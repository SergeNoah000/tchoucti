/**
 * Shared API types — kept in one place so screens stay typed.
 * These mirror backend Pydantic schemas.
 */

export type UUID = string;

export interface Groupement {
  id: UUID;
  name: string;
  slug: string;
  subdomain: string;
  custom_domain?: string | null;
  description?: string | null;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
  city?: string | null;
  country: string;
  logo_url?: string | null;
  primary_color: string;
  is_active: boolean;
  subscription_status: string;
  trial_ends_at?: string | null;
  subscription_ends_at?: string | null;
  max_associations: number;
  max_users: number;
  created_at: string;
  updated_at: string;
}

export type AssociationType = "tontine" | "mutuelle" | "cooperative" | "association" | "autre";

export type SettingsFrequency = "weekly" | "biweekly" | "monthly" | "quarterly";
export type TontineAllocation =
  | "fixed_order"
  | "random_draw"
  | "auction"
  | "urgency_priority"
  | "member_vote";
export type MeetingMode = "physical" | "virtual" | "hybrid";

/** Operational settings stored in `Association.config` (JSONB). All optional. */
export interface AssociationConfig {
  tontine?: {
    contribution_amount?: number;
    frequency?: SettingsFrequency;
    cycle_duration_months?: number;
    participants_count?: number;
    allocation_method?: TontineAllocation;
  };
  social_fund?: {
    contribution_amount?: number;
    conditions?: string;
    events?: {
      death?: number;
      illness?: number;
      marriage?: number;
      birth?: number;
    };
  };
  payments?: {
    cash?: boolean;
    mtn_momo?: boolean;
    orange_money?: boolean;
    bank_transfer?: boolean;
  };
  meetings?: {
    frequency?: SettingsFrequency;
    mode?: MeetingMode;
    quorum?: number;
    auto_notify?: boolean;
  };
  notifications?: {
    contribution_reminder?: boolean;
    meeting?: boolean;
    penalty?: boolean;
    tour_allocation?: boolean;
    birthday?: boolean;
    loan_due?: boolean;
  };
}

export interface Association {
  id: UUID;
  groupement_id: UUID;
  name: string;
  slug: string;
  description?: string | null;
  type: AssociationType;
  email?: string | null;
  phone?: string | null;
  logo_url?: string | null;
  primary_color: string;
  currency: string;
  currency_locked?: boolean;
  groupement_subdomain?: string | null;
  timezone: string;
  address?: string | null;
  city?: string | null;
  config: AssociationConfig;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type Gender = "male" | "female" | "other";

export interface User {
  id: UUID;
  email: string;
  full_name: string;
  phone?: string | null;
  /** Profil personnel — modifiable par l'utilisateur lui-même. */
  address?: string | null;
  gender?: Gender | null;
  birth_date?: string | null;
  profession?: string | null;
  is_active: boolean;
  /** Mutually exclusive role flags. `is_association_admin` is now strict: only
   *  true when the user has the `association_admin` role on a membership. */
  is_platform_admin: boolean;
  is_groupement_admin?: boolean;
  is_association_admin?: boolean;
  /** True for any operational association role (treasurer, secretary, manager,
   *  member). Used to route to the operational dashboard instead of /onboarding. */
  has_association_role?: boolean;
  /** True if the user holds any role other than plain "member" on a membership
   *  (treasurer, secretary, manager, admin). Unlocks bureau actions in séances. */
  has_bureau_role?: boolean;
  avatar_url?: string | null;
  groupement_id?: UUID | null;
  created_at: string;
}

export type RoleCode =
  | "super_admin"
  | "groupement_admin"
  | "association_admin"
  | "president"
  | "vice_president"
  | "secretary"
  | "treasurer"
  | "censor"
  | "manager"
  | "member";

export type MembershipStatus = "active" | "suspended" | "resigned";

/** Member category — tunable by the association admin. */
export type MemberCategory = "active" | "honorary" | "founder" | "suspended";

/** Brief user shape nested in a membership (backend UserBrief). */
export interface UserBrief {
  id: UUID;
  full_name: string;
  email: string;
  phone?: string | null;
  is_active: boolean;
}

/** Role attached to a membership (backend RoleOut). */
export interface AssocRole {
  id: UUID;
  name: string;
  code: string;
  description?: string | null;
  scope: string;
  is_system: boolean;
  groupement_id?: UUID | null;
  association_id?: UUID | null;
}

export interface Membership {
  id: UUID;
  user_id: UUID;
  association_id: UUID;
  member_number?: string | null;
  status: MembershipStatus;
  category: MemberCategory;
  joined_at: string;
  left_at?: string | null;
  cumulative_contributions: number;
  notes?: string | null;
  user: UserBrief;
  roles: AssocRole[];
  created_at: string;
  updated_at: string;
  /** Populated only on create (when an invite email was sent). */
  activation_url?: string | null;
  /** Populated only by the groupement-wide members roll-up. */
  association_name?: string | null;
}

// ── Caisse ───────────────────────────────────────────────────────────────

export type CaisseCategoryT = "system" | "collective" | "project" | "personal";
export type InterestDistributionT = "kept" | "shared_pro_rata";
export type DistributionPeriodT = "per_meeting" | "monthly" | "quarterly" | "annually";
export type WithdrawalModeT = "never" | "anytime_if_liquid" | "end_of_period_only";

export interface Caisse {
  id: UUID;
  fund_id: UUID;
  fund_kind?: string | null;
  name: string;
  slug: string;
  description?: string | null;
  category: CaisseCategoryT;
  is_system: boolean;
  is_active: boolean;
  is_recurring: boolean;
  recurring_amount: number;
  is_member_required: boolean;
  member_required_amount: number;
  has_ceiling: boolean;
  ceiling_amount: number;
  has_objective: boolean;
  objective_amount: number;
  objective_deadline?: string | null;
  // Phase 7 (Fred)
  interest_distribution: InterestDistributionT;
  distribution_period: DistributionPeriodT;
  withdrawal_mode: WithdrawalModeT;
  last_distribution_at?: string | null;
}

export interface CaisseContributorBalance {
  membership_id: UUID;
  member_name?: string | null;
  apport_cum: number;
  apport_cum_at_period_start: number;
  interest_cum: number;
}

export interface CaisseDistributionShare {
  membership_id: UUID;
  member_name?: string | null;
  base: number;
  share_amount: number;
}

export interface CaisseDistribution {
  id: UUID;
  caisse_id: UUID;
  period_start: string;
  period_end: string;
  period_label: string;
  interest_pool: number;
  total_base: number;
  closed_at: string;
  closed_by_id?: UUID | null;
  shares: CaisseDistributionShare[];
}

export interface MyShareItem {
  caisse_id: UUID;
  caisse_name: string;
  caisse_slug: string;
  category: CaisseCategoryT;
  interest_distribution: InterestDistributionT;
  apport_cum: number;
  interest_cum: number;
  total_apport: number;
  last_distribution_at?: string | null;
}

// ── Tontine ──────────────────────────────────────────────────────────────

export type TontineCycleStatus = "draft" | "active" | "completed" | "cancelled";
export type TontineRoundStatus = "pending" | "collecting" | "paid_out" | "skipped";

export interface TontineBeneficiary {
  membership_id: UUID;
  name?: string | null;
  share_amount: number;
  share_parts: number;
}

export interface TontineRound {
  id: UUID;
  round_number: number;
  scheduled_date?: string | null;
  paid_out_date?: string | null;
  /** A round can be split among multiple beneficiaries (shared pot). */
  beneficiaries: TontineBeneficiary[];
  expected_amount: number;
  collected_amount: number;
  paid_out_amount: number;
  status: TontineRoundStatus;
  /** Phase 2c — séance qui héberge ce tour (null si pas encore mappée). */
  meeting_id?: UUID | null;
  meeting_title?: string | null;
}

/** Phase 6A : un cycle = une rotation complète, enfant d'une Tontine. */
export interface TontineCycle {
  id: UUID;
  tontine_id: UUID;
  cycle_number: number;
  round_amount: number;
  rounds_count: number;
  current_round_number: number;
  start_date: string;
  end_date?: string | null;
  order_strategy: string;
  status: TontineCycleStatus;
  is_mandatory: boolean;
  created_at: string;
}

export interface TontineCycleDetail extends TontineCycle {
  rounds: TontineRound[];
  pot_amount: number;
}

/** Phase 6A : la tontine durable, parent des cycles. */
export interface Tontine {
  id: UUID;
  association_id: UUID;
  name: string;
  slug: string;
  description?: string | null;
  is_active: boolean;
  round_amount: number;
  frequency: string;
  custom_interval_days?: number | null;
  beneficiaries_per_round: number;
  beneficiary_pays: boolean;
  selection_method: string;
  created_at: string;
  cycles_count: number;
  current_cycle?: TontineCycleOut | null;
}

/** Résumé de cycle (sans les tours) — pour la liste/le current_cycle. */
export type TontineCycleOut = TontineCycle;

export interface TontineDetail extends Tontine {
  current_cycle?: TontineCycleDetail | null;
  cycles: TontineCycleDetail[];
}

export type PermissionCode =
  | "groupements.view" | "groupements.edit"
  | "associations.view" | "associations.create" | "associations.edit" | "associations.delete"
  | "members.view" | "members.invite" | "members.edit" | "members.remove"
  | "roles.view" | "roles.assign"
  | "meetings.view" | "meetings.create" | "meetings.edit" | "meetings.close" | "meetings.delete"
  | "meetings.record_activity" | "meetings.record_attendance"
  | "finance.view" | "finance.record_movement" | "finance.transfer" | "finance.adjust"
  | "loans.view" | "loans.request" | "loans.approve" | "loans.disburse" | "loans.record_repayment"
  | "tontines.view" | "tontines.create" | "tontines.manage"
  | "social_aid.view" | "social_aid.declare" | "social_aid.approve" | "social_aid.payout"
  | "projects.view" | "projects.create" | "projects.manage"
  | "documents.view" | "documents.upload" | "documents.delete"
  | "reports.view" | "reports.export"
  | "audit.view"
  | "settings.view" | "settings.edit";

export type MeetingStatus = "planned" | "ongoing" | "closed" | "cancelled";
export type AttendanceStatus = "present" | "absent" | "excused" | "late";
export type EntryStatus = "draft" | "recorded" | "corrected" | "voided";

export type ActivityType =
  | "monthly_contribution"
  | "insurance_contribution"
  | "tontine_contribution"
  | "loan_repayment"
  | "penalty"
  | "savings_deposit"
  | "exceptional_donation"
  | "project_contribution"
  | "other";

export interface Activity {
  id: UUID;
  association_id: UUID;
  type: ActivityType;
  code: string;
  name: string;
  description?: string | null;
  color: string;
  icon?: string | null;
  config: Record<string, unknown>;
  is_visible_in_meeting: boolean;
  is_required: boolean;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// ── Finance ──────────────────────────────────────────────────────────────

export type FundKind = "general" | "tontine" | "insurance" | "savings" | "project" | "external";
export type MovementDirection = "in" | "out" | "xfer";

export interface Fund {
  id: UUID;
  kind: FundKind;
  ref_key: string;
  name: string;
  description?: string | null;
  balance: number;
  is_locked: boolean;
  is_system: boolean;
}

export interface Treasury {
  id: UUID;
  association_id: UUID;
  balance: number;
  currency: string;
  is_locked: boolean;
  funds: Fund[];
}

export interface TreasuryMovement {
  id: UUID;
  direction: MovementDirection;
  amount: number;
  balance_after: number;
  occurred_on: string;
  source_type: string;
  source_id?: UUID | null;
  related_membership_id?: UUID | null;
  description?: string | null;
  is_voided: boolean;
  created_at: string;
}

export interface Meeting {
  id: UUID;
  association_id: UUID;
  title: string;
  description?: string | null;
  scheduled_on: string;
  started_at?: string | null;
  closed_at?: string | null;
  location?: string | null;
  status: MeetingStatus;
  facilitator_id?: UUID | null;
  created_by_id?: UUID | null;
  agenda: Record<string, unknown>;
  notes?: string | null;
  report_url?: string | null;
  total_in: number;
  total_out: number;
  created_at: string;
  updated_at: string;
}

export interface MeetingDetail extends Meeting {
  attendances: MeetingAttendance[];
  entries: MeetingActivityEntry[];
}

export interface MeetingAttendance {
  id: UUID;
  meeting_id: UUID;
  membership_id: UUID;
  status: AttendanceStatus;
  notes?: string | null;
  excuse_reason?: string | null;
}

export interface MeetingActivityEntry {
  id: UUID;
  meeting_id: UUID;
  membership_id: UUID;
  activity_id: UUID;
  amount: number;
  data: Record<string, unknown>;
  status: EntryStatus;
  movement_id?: UUID | null;
  recorded_by_id?: UUID | null;
  recorded_at?: string | null;
  corrects_entry_id?: UUID | null;
  correction_reason?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}


export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

// ── Invitations & groupement admin team ──────────────────────────────────

export type InvitationKind =
  | "groupement_admin"
  | "association_admin"
  | "association_member";

export type InvitationStatus = "pending" | "accepted" | "expired" | "revoked";

export interface Invitation {
  id: UUID;
  email: string;
  kind: InvitationKind;
  status: InvitationStatus;
  full_name?: string | null;
  message?: string | null;
  groupement_id?: UUID | null;
  association_id?: UUID | null;
  invited_by_id?: UUID | null;
  expires_at: string;
  sent_at?: string | null;
  accepted_at?: string | null;
  resent_count: number;
  created_at: string;
}

/** Returned right after creating/resending — embeds the one-time activation URL. */
export interface InvitationCreated extends Invitation {
  activation_url: string;
}

export interface GroupementAdmin {
  id: UUID;
  user_id: UUID;
  groupement_id: UUID;
  is_owner: boolean;
  added_at: string;
  user_email?: string | null;
  user_full_name?: string | null;
  user_is_active?: boolean | null;
}

export interface AssociationBranding {
  groupement: {
    name: string;
    slug: string;
    subdomain: string;
    logo_url?: string | null;
    primary_color: string;
  };
  association: {
    name: string;
    slug: string;
    logo_url?: string | null;
    primary_color: string;
  };
}

export interface InvitationPeek {
  email: string;
  full_name?: string | null;
  kind: InvitationKind;
  groupement_name?: string | null;
  association_name?: string | null;
  expires_at: string;
  invited_by_name?: string | null;
  existing_active?: boolean;
}

// ── Social aid ───────────────────────────────────────────────────────────

export type SocialAidKind = "death" | "illness" | "marriage" | "birth" | "other";
export type SocialAidStatus =
  | "requested"
  | "reviewing"
  | "approved"
  | "paid"
  | "rejected"
  | "cancelled";

export interface SocialAidPayout {
  id: UUID;
  paid_on: string;
  amount: number;
  movement_id?: UUID | null;
  notes?: string | null;
}

export interface SocialAidCase {
  id: UUID;
  association_id: UUID;
  beneficiary_membership_id: UUID;
  beneficiary_name?: string | null;
  reference: string;
  kind: SocialAidKind;
  status: SocialAidStatus;
  title: string;
  description?: string | null;
  event_date?: string | null;
  requested_on: string;
  decided_on?: string | null;
  requested_amount?: number | null;
  approved_amount: number;
  paid_amount: number;
  rejection_reason?: string | null;
  created_at: string;
}

export interface SocialAidCaseDetail extends SocialAidCase {
  payouts: SocialAidPayout[];
}

// ── Loans ────────────────────────────────────────────────────────────────

export type LoanStatus =
  | "requested"
  | "approved"
  | "disbursed"
  | "repaying"
  | "paid"
  | "rejected"
  | "defaulted"
  | "cancelled";

export type LoanInstallmentStatus = "pending" | "partially_paid" | "paid" | "late" | "waived";

export interface LoanInstallment {
  id: UUID;
  number: number;
  due_on: string;
  principal_part: number;
  interest_part: number;
  expected_amount: number;
  paid_principal: number;
  paid_interest: number;
  paid_late_fee: number;
  paid_on?: string | null;
  status: LoanInstallmentStatus;
}

export interface LoanRepayment {
  id: UUID;
  paid_on: string;
  total_paid: number;
  principal: number;
  interest: number;
  late_fee: number;
  movement_id?: UUID | null;
}

export interface Loan {
  id: UUID;
  association_id: UUID;
  borrower_membership_id: UUID;
  borrower_name?: string | null;
  reference: string;
  principal: number;
  /** Decimal — serialised as a string by the backend. */
  interest_rate_pct: string;
  late_fee_pct: string;
  duration_months: number;
  total_interest: number;
  total_due: number;
  installment_amount: number;
  paid_principal: number;
  paid_interest: number;
  paid_late_fees: number;
  remaining_balance: number;
  requested_on: string;
  approved_on?: string | null;
  disbursed_on?: string | null;
  first_due_on?: string | null;
  last_due_on?: string | null;
  status: LoanStatus;
  purpose?: string | null;
  created_at: string;
}

export interface LoanDetail extends Loan {
  installments: LoanInstallment[];
  repayments: LoanRepayment[];
}
