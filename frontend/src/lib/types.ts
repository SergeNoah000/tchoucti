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

export interface Association {
  id: UUID;
  groupement_id: UUID;
  name: string;
  slug: string;
  description?: string | null;
  logo_url?: string | null;
  primary_color: string;
  currency: string;
  timezone: string;
  address?: string | null;
  city?: string | null;
  config: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface User {
  id: UUID;
  email: string;
  full_name: string;
  phone?: string | null;
  is_active: boolean;
  /** Mutually exclusive role flags — backend sets exactly zero or one of these. */
  is_platform_admin: boolean;
  is_groupement_admin?: boolean;
  is_association_admin?: boolean;
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

export interface Fund {
  id: UUID;
  treasury_id: UUID;
  code: string;
  name: string;
  balance: number;
  is_system: boolean;
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

export interface InvitationPeek {
  email: string;
  full_name?: string | null;
  kind: InvitationKind;
  groupement_name?: string | null;
  expires_at: string;
  invited_by_name?: string | null;
}
