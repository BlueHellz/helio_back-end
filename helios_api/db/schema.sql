-- ═══════════════════════════════════════════════════════════════════════════════
-- Black Light — Postgres schema for Supabase
-- Execute in Supabase SQL editor (manual). References auth.users(id) for profiles.
--
-- POLICY INTENT (comments + SQL):
-- authenticated users CRUD aligned with org membership and ownership.
-- Backend uses service-role in API routes; policies protect direct Postgres
-- clients (anon key + JWT). Backend must still authorize in application logic.
--
-- IMPORTANT: FK order requires orgs BEFORE profiles.profiles.org_id → orgs(id)
-- ═══════════════════════════════════════════════════════════════════════════════

-- Extensions (Supabase provides pgcrypto for gen_random_uuid)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── orgs (created first: profiles references orgs) ───────────────────────────
CREATE TABLE orgs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    design_mode BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ─── profiles ─────────────────────────────────────────────────────────────────
CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('homeowner','installer','drone_op','investor','admin')),
    full_name TEXT,
    company_name TEXT,
    phone TEXT,
    wallet_address TEXT,
    org_id UUID REFERENCES orgs(id),
    completed_projects_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_profiles_org_id ON profiles(org_id);

-- ─── custom fields & roles ───────────────────────────────────────────────────
CREATE TABLE custom_field_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    field_type TEXT NOT NULL CHECK (field_type IN (
        'text','number','date','dropdown','multi_select','file','photo','toggle',
        'url','phone','email','currency','formula'
    )),
    options JSONB DEFAULT '[]',
    is_global BOOLEAN DEFAULT false,
    target_sections JSONB DEFAULT '[]',
    visibility_rules JSONB DEFAULT '{}',
    sort_order INTEGER DEFAULT 0,
    required BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE custom_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    permissions JSONB DEFAULT '{}',
    is_default BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE user_roles (
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    role_id UUID REFERENCES custom_roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

-- ─── projects ─────────────────────────────────────────────────────────────────
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES orgs(id),
    user_id UUID NOT NULL REFERENCES profiles(id),
    address TEXT NOT NULL,
    project_type TEXT DEFAULT 'residential' CHECK (project_type IN ('residential','commercial','industrial')),
    roof_data JSONB,
    panel_layout JSONB,
    electrical_spec JSONB,
    financial_summary JSONB,
    custom_data JSONB DEFAULT '{}',
    status TEXT DEFAULT 'draft' CHECK (status IN (
        'draft','designed','drone_requested','drone_completed','permit_submitted',
        'permitted','installed','inspected','completed'
    )),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_projects_user_id ON projects(user_id);
CREATE INDEX idx_projects_org_id ON projects(org_id);

-- ─── chat / contracts ─────────────────────────────────────────────────────────
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    messages JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    file_url TEXT,
    signed_at TIMESTAMPTZ,
    signature_data TEXT,
    status TEXT DEFAULT 'uploaded' CHECK (status IN ('uploaded','signed','sent'))
);

-- ─── CRM pipelines ────────────────────────────────────────────────────────────
CREATE TABLE pipelines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE pipeline_stages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    trigger_condition JSONB DEFAULT '{}',
    color TEXT DEFAULT '#0066FF'
);

CREATE TABLE crm_deals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_stage_id UUID REFERENCES pipeline_stages(id),
    project_id UUID REFERENCES projects(id),
    custom_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ─── drone ────────────────────────────────────────────────────────────────────
CREATE TABLE scan_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    drone_op_id UUID REFERENCES profiles(id),
    status TEXT DEFAULT 'pending' CHECK (status IN (
        'pending','accepted','in_progress','scan_uploaded','ai_validated',
        'payment_5_released','permit_issued','payment_20_released','installed','payment_75_released'
    )),
    video_upload_path TEXT,
    payment_total_hlio NUMERIC DEFAULT 0,
    payment_tranches JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE drone_op_ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES scan_jobs(id) ON DELETE CASCADE,
    rater_id UUID REFERENCES profiles(id),
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    comment TEXT
);

-- ─── pools / investments ─────────────────────────────────────────────────────
CREATE TABLE pools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES orgs(id),
    name TEXT NOT NULL,
    description TEXT,
    target_amount_hlio NUMERIC,
    raised_amount_hlio NUMERIC DEFAULT 0,
    investor_count INTEGER DEFAULT 0,
    governance_token_symbol TEXT,
    terms_json JSONB,
    status TEXT DEFAULT 'fundraising' CHECK (status IN ('fundraising','active','closed'))
);

CREATE TABLE pool_investments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pool_id UUID REFERENCES pools(id) ON DELETE CASCADE,
    investor_id UUID REFERENCES profiles(id),
    amount_hlio NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE pool_governance_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pool_id UUID REFERENCES pools(id) UNIQUE,
    token_symbol TEXT NOT NULL,
    is_tradable BOOLEAN DEFAULT false,
    listing_fee_paid BOOLEAN DEFAULT false,
    trading_royalty_bps INTEGER DEFAULT 15,
    metrics_met BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ─── marketplace ─────────────────────────────────────────────────────────────
CREATE TABLE marketplace_listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id UUID REFERENCES profiles(id),
    product_type TEXT NOT NULL,
    product_model TEXT,
    unit_price NUMERIC,
    available_quantity INTEGER,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE marketplace_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id UUID REFERENCES marketplace_listings(id),
    buyer_id UUID REFERENCES profiles(id),
    project_id UUID REFERENCES projects(id),
    quantity INTEGER,
    total_cost NUMERIC,
    platform_fee NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ─── HLIO / revenue ───────────────────────────────────────────────────────────
CREATE TABLE hlio_wallets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) UNIQUE,
    public_key TEXT,
    balance NUMERIC DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE minting_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    amount_hlio NUMERIC,
    tx_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE revenue_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES orgs(id),
    project_id UUID REFERENCES projects(id),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'rev_share','marketplace_fee','pool_token_listing_fee','pool_token_trade_royalty'
    )),
    amount NUMERIC,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ─── org UI layouts (section-based JSON) ──────────────────────────────────────
CREATE TABLE org_layouts (
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    section TEXT NOT NULL,
    layout JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (org_id, section)
);

-- ─── updated_at triggers ───────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_custom_field_definitions_updated
  BEFORE UPDATE ON custom_field_definitions
  FOR EACH ROW EXECUTE PROCEDURE set_updated_at();

CREATE TRIGGER trg_projects_updated
  BEFORE UPDATE ON projects
  FOR EACH ROW EXECUTE PROCEDURE set_updated_at();

CREATE TRIGGER trg_crm_deals_updated
  BEFORE UPDATE ON crm_deals
  FOR EACH ROW EXECUTE PROCEDURE set_updated_at();

-- ═══════════════════════════════════════════════════════════════════════════════
-- ROW LEVEL SECURITY
-- Supabase: role "authenticated" + auth.uid(). Service role bypasses RLS.
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE orgs ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE custom_field_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE custom_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipelines ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE crm_deals ENABLE ROW LEVEL SECURITY;
ALTER TABLE scan_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE drone_op_ratings ENABLE ROW LEVEL SECURITY;
ALTER TABLE pools ENABLE ROW LEVEL SECURITY;
ALTER TABLE pool_investments ENABLE ROW LEVEL SECURITY;
ALTER TABLE pool_governance_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketplace_listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketplace_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE hlio_wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE minting_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE revenue_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE org_layouts ENABLE ROW LEVEL SECURITY;

-- Helper function: UUIDs for org memberships of the JWT subject (for policy reuse)
CREATE OR REPLACE FUNCTION public.user_org_ids()
RETURNS SETOF UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT org_id FROM profiles WHERE id = auth.uid() AND org_id IS NOT NULL
  UNION
  SELECT o.id FROM orgs o
    JOIN profiles p ON p.id = auth.uid()
  WHERE p.role = 'admin'
$$;

COMMENT ON FUNCTION public.user_org_ids() IS
  'Used by policies: admins see extra org IDs; installers see membership org_id. Tune for your RBAC.';

-- ─── profiles ───
CREATE POLICY profiles_select_own ON profiles FOR SELECT TO authenticated USING (id = auth.uid());
CREATE POLICY profiles_update_own ON profiles FOR UPDATE TO authenticated USING (id = auth.uid());
CREATE POLICY profiles_insert_own ON profiles FOR INSERT TO authenticated WITH CHECK (id = auth.uid());

-- ─── orgs ───
CREATE POLICY orgs_select_member ON orgs FOR SELECT TO authenticated USING (
  id IN (SELECT user_org_ids())
  OR EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin')
);
CREATE POLICY orgs_update_member ON orgs FOR UPDATE TO authenticated USING (
  id IN (SELECT user_org_ids())
  OR EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role IN ('installer','admin'))
);

-- ─── Org-scoped configuration ───
CREATE POLICY custom_field_defs_org ON custom_field_definitions FOR ALL TO authenticated USING (org_id IN (SELECT user_org_ids())) WITH CHECK (org_id IN (SELECT user_org_ids()));
CREATE POLICY custom_roles_org ON custom_roles FOR ALL TO authenticated USING (org_id IN (SELECT user_org_ids())) WITH CHECK (org_id IN (SELECT user_org_ids()));

CREATE POLICY user_roles_select_own ON user_roles FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY user_roles_org_writes ON user_roles FOR ALL TO authenticated
  USING (EXISTS (
    SELECT 1 FROM custom_roles cr JOIN profiles pf ON pf.id = auth.uid()
    WHERE cr.id = user_roles.role_id AND cr.org_id = pf.org_id AND pf.role IN ('installer','admin')
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM custom_roles cr JOIN profiles pf ON pf.id = auth.uid()
    WHERE cr.id = user_roles.role_id AND cr.org_id = pf.org_id AND pf.role IN ('installer','admin')
  ));

-- ─── projects (owner org / member read) ───
CREATE POLICY projects_select ON projects FOR SELECT TO authenticated USING (
  user_id = auth.uid()
  OR org_id IN (SELECT user_org_ids())
  OR EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin')
);
CREATE POLICY projects_insert ON projects FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY projects_update ON projects FOR UPDATE TO authenticated
  USING (user_id = auth.uid() OR org_id IN (SELECT user_org_ids()))
  WITH CHECK (user_id = auth.uid() OR org_id IN (SELECT user_org_ids()));
CREATE POLICY projects_delete ON projects FOR DELETE TO authenticated
  USING (user_id = auth.uid() OR org_id IN (SELECT user_org_ids()));

-- ─── chat_sessions (via owning project) ───
CREATE POLICY chats_project ON chat_sessions FOR ALL TO authenticated USING (
  project_id IS NULL OR EXISTS (
    SELECT 1 FROM projects pr WHERE pr.id = chat_sessions.project_id AND (
      pr.user_id = auth.uid() OR pr.org_id IN (SELECT user_org_ids())
    )
  )
);

-- ─── contracts (via project) ───
CREATE POLICY contracts_project ON contracts FOR ALL TO authenticated USING (
  EXISTS (
    SELECT 1 FROM projects pr WHERE pr.id = contracts.project_id AND (
      pr.user_id = auth.uid() OR pr.org_id IN (SELECT user_org_ids())
    )
  )
);

-- ─── pipelines / stages ───
CREATE POLICY pipelines_org ON pipelines FOR ALL TO authenticated USING (org_id IN (SELECT user_org_ids())) WITH CHECK (org_id IN (SELECT user_org_ids()));
CREATE POLICY pipeline_stages_org ON pipeline_stages FOR ALL TO authenticated USING (
  EXISTS (SELECT 1 FROM pipelines pl WHERE pl.id = pipeline_id AND pl.org_id IN (SELECT user_org_ids()))
) WITH CHECK (
  EXISTS (SELECT 1 FROM pipelines pl WHERE pl.id = pipeline_id AND pl.org_id IN (SELECT user_org_ids()))
);

CREATE POLICY crm_deals_access ON crm_deals FOR ALL TO authenticated USING (
  EXISTS (SELECT 1 FROM pipeline_stages ps JOIN pipelines pl ON pl.id = ps.pipeline_id WHERE ps.id = crm_deals.pipeline_stage_id AND pl.org_id IN (SELECT user_org_ids()))
  OR EXISTS (SELECT 1 FROM projects pr WHERE pr.id = crm_deals.project_id AND (pr.user_id = auth.uid() OR pr.org_id IN (SELECT user_org_ids())))
);

-- ─── drone ───
CREATE POLICY scan_jobs_access ON scan_jobs FOR ALL TO authenticated USING (
  drone_op_id = auth.uid()
  OR EXISTS (SELECT 1 FROM projects pr WHERE pr.id = scan_jobs.project_id AND (pr.user_id = auth.uid() OR pr.org_id IN (SELECT user_org_ids())))
);
CREATE POLICY drone_ratings ON drone_op_ratings FOR ALL TO authenticated USING (
  EXISTS (SELECT 1 FROM scan_jobs j WHERE j.id = job_id AND (j.drone_op_id = auth.uid() OR EXISTS (SELECT 1 FROM projects pr WHERE pr.id = j.project_id AND pr.user_id = auth.uid())))
);

-- ─── pools / marketplace / wallets / revenue ───
CREATE POLICY pools_org_or_public ON pools FOR SELECT TO authenticated USING (true); -- widen read MVP; tighten to org or role
CREATE POLICY pools_write_org ON pools FOR INSERT TO authenticated WITH CHECK (org_id IS NULL OR org_id IN (SELECT user_org_ids()));
CREATE POLICY pool_investments_self ON pool_investments FOR ALL TO authenticated USING (investor_id = auth.uid() OR EXISTS (
  SELECT 1 FROM pools pp WHERE pp.id = pool_id AND pp.org_id IN (SELECT user_org_ids())
));
CREATE POLICY pool_tokens ON pool_governance_tokens FOR ALL TO authenticated USING (
  EXISTS (SELECT 1 FROM pools pp WHERE pp.id = pool_id AND (pp.org_id IN (SELECT user_org_ids())))
);

CREATE POLICY marketplace_supplier ON marketplace_listings FOR ALL TO authenticated USING (supplier_id = auth.uid())
  WITH CHECK (supplier_id = auth.uid());
CREATE POLICY marketplace_orders ON marketplace_orders FOR ALL TO authenticated USING (
  buyer_id = auth.uid() OR EXISTS (
    SELECT 1 FROM marketplace_listings ml WHERE ml.id = listing_id AND ml.supplier_id = auth.uid()
  )
);

CREATE POLICY hlio_wallet_own ON hlio_wallets FOR ALL TO authenticated USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
CREATE POLICY minting_read ON minting_events FOR SELECT TO authenticated USING (
  EXISTS (SELECT 1 FROM projects pr WHERE pr.id = minting_events.project_id AND (pr.user_id = auth.uid() OR pr.org_id IN (SELECT user_org_ids())))
);
CREATE POLICY revenue_org ON revenue_events FOR ALL TO authenticated USING (org_id IN (SELECT user_org_ids()));

CREATE POLICY org_layouts_org ON org_layouts FOR ALL TO authenticated USING (org_id IN (SELECT user_org_ids())) WITH CHECK (org_id IN (SELECT user_org_ids()));

COMMENT ON SCHEMA public IS 'RLS + Black Light: review projects_update WITH CHECK and pools SELECT before production hardening.';

