import axios, { AxiosError } from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:18000/api";

export const api = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
  withCredentials: false,
});

// Public API (no auth interceptor)
export const publicApi = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
});

// ---------- Auth interceptors ----------
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let isRefreshing = false;
let failedQueue: Array<{ resolve: (v?: unknown) => void; reject: (r?: unknown) => void }> = [];

const flushQueue = (err: unknown, token: string | null = null) => {
  failedQueue.forEach((p) => (err ? p.reject(err) : p.resolve(token)));
  failedQueue = [];
};

const handleAuthExpired = () => {
  if (typeof window === "undefined") return;
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("auth-storage");
  setTimeout(() => {
    if (!window.location.pathname.includes("/login")) {
      window.location.replace("/login?expired=true");
    }
  }, 80);
};

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as typeof error.config & { _retry?: boolean };
    if (!original) return Promise.reject(error);

    // 403 → redirect to access-denied (handled by app shell, not here)
    if (error.response?.status === 403) return Promise.reject(error);

    // 401 → try refresh once
    if (error.response?.status === 401 && !original._retry) {
      const url = original.url || "";
      if (url.includes("/auth/login") || url.includes("/auth/refresh")) {
        return Promise.reject(error);
      }
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            if (original.headers) original.headers.Authorization = `Bearer ${token}`;
            return api(original);
          })
          .catch((e) => Promise.reject(e));
      }
      original._retry = true;
      isRefreshing = true;
      try {
        const refresh = typeof window !== "undefined" ? localStorage.getItem("refresh_token") : null;
        if (!refresh) throw new Error("No refresh token");
        const { data } = await axios.post(`${API_URL}/auth/refresh`, { refresh_token: refresh });
        localStorage.setItem("access_token", data.access_token);
        if (data.refresh_token) localStorage.setItem("refresh_token", data.refresh_token);
        flushQueue(null, data.access_token);
        if (original.headers) original.headers.Authorization = `Bearer ${data.access_token}`;
        return api(original);
      } catch (e) {
        flushQueue(e, null);
        handleAuthExpired();
        return Promise.reject(e);
      } finally {
        isRefreshing = false;
      }
    }
    return Promise.reject(error);
  }
);

// ---------- API namespaces ----------
export const authApi = {
  login: async (email: string, password: string) => {
    const body = new URLSearchParams();
    body.append("username", email);
    body.append("password", password);
    const { data } = await api.post("/auth/login", body, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    return data;
  },
  logout: async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      if (typeof window !== "undefined") {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
      }
    }
  },
  getMe: async () => (await api.get("/auth/me")).data,
  activate: async (token: string, password: string) =>
    (await publicApi.post("/auth/activate", { token, password })).data,
};

export const tenantApi = {
  whoami: async () => (await publicApi.get("/whoami-tenant")).data,
};

export const groupementsApi = {
  list: async () => (await api.get("/groupements")).data,
  get: async (id: string) => (await api.get(`/groupements/${id}`)).data,
  getMine: async () => (await api.get("/groupements/me")).data,
  create: async (payload: Record<string, unknown>) => (await api.post("/groupements", payload)).data,
  update: async (id: string, payload: Record<string, unknown>) => (await api.patch(`/groupements/${id}`, payload)).data,
  // Admin team
  listAdmins: async (id: string) => (await api.get(`/groupements/${id}/admins`)).data,
  inviteAdmin: async (id: string, payload: { email: string; full_name?: string; message?: string }) =>
    (await api.post(`/groupements/${id}/admins`, payload)).data,
  removeAdmin: async (id: string, userId: string) =>
    (await api.delete(`/groupements/${id}/admins/${userId}`)).data,
  transferOwnership: async (id: string, targetUserId: string) =>
    (await api.post(`/groupements/${id}/transfer-ownership`, { target_user_id: targetUserId })).data,
  listInvitations: async (id: string, onlyPending = true) =>
    (await api.get(`/groupements/${id}/invitations`, { params: { only_pending: onlyPending } })).data,
  listMembers: async (id: string, associationId?: string) =>
    (await api.get(`/groupements/${id}/members`, {
      params: associationId ? { association_id: associationId } : undefined,
    })).data,
};

export const invitationsApi = {
  resend: async (invitationId: string) =>
    (await api.post(`/invitations/${invitationId}/resend`, {})).data,
  revoke: async (invitationId: string) =>
    (await api.post(`/invitations/${invitationId}/revoke`, {})).data,
  peek: async (token: string) =>
    (await publicApi.get("/invitations/peek", { params: { token } })).data,
  accept: async (payload: { token: string; password?: string; full_name?: string }) =>
    (await publicApi.post("/invitations/accept", payload)).data,
};

export const associationsApi = {
  list: async (groupementId?: string) =>
    (await api.get("/associations", { params: groupementId ? { groupement_id: groupementId } : undefined })).data,
  get: async (id: string) => (await api.get(`/associations/${id}`)).data,
  create: async (payload: Record<string, unknown>) => (await api.post("/associations", payload)).data,
  update: async (id: string, payload: Record<string, unknown>) =>
    (await api.patch(`/associations/${id}`, payload)).data,
};

// ── Setup wizard (config-v2, admin only) ───────────────────────────────────
export const setupApi = {
  /** Where the admin is in the onboarding wizard. */
  getState: async (associationId: string) =>
    (await api.get(`/associations/${associationId}/setup`)).data as {
      setup_complete: boolean;
      setup_step: number;
    },
  /** Advance the wizard step or mark setup_complete=true. Idempotent. */
  advance: async (
    associationId: string,
    payload: { step?: number; complete?: boolean },
  ) => (await api.patch(`/associations/${associationId}/setup`, payload)).data,
  setRegistrationFee: async (associationId: string, amount: number) =>
    (await api.patch(`/associations/${associationId}/registration-fee`, {
      registration_fee: amount,
    })).data,

  // Critères d'adhésion
  listCriteria: async (associationId: string) =>
    (await api.get(`/associations/${associationId}/criteria`)).data,
  addCriterion: async (
    associationId: string,
    payload: {
      type: string;
      label: string;
      value: string;
      is_required?: boolean;
      sort_order?: number;
    },
  ) => (await api.post(`/associations/${associationId}/criteria`, payload)).data,
  deleteCriterion: async (associationId: string, criterionId: string) =>
    (await api.delete(`/associations/${associationId}/criteria/${criterionId}`)).data,

  // Documents légaux
  listDocuments: async (associationId: string) =>
    (await api.get(`/associations/${associationId}/documents`)).data,
  uploadDocument: async (
    associationId: string,
    file: File,
    title: string,
    kind: string,
    description?: string,
  ) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("title", title);
    fd.append("kind", kind);
    if (description) fd.append("description", description);
    return (
      await api.post(`/associations/${associationId}/documents`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      })
    ).data;
  },
  deleteDocument: async (associationId: string, documentId: string) =>
    (await api.delete(`/associations/${associationId}/documents/${documentId}`)).data,
  uploadLogo: async (associationId: string, file: File): Promise<{ logo_url: string }> => {
    const fd = new FormData();
    fd.append("file", file);
    return (
      await api.post(`/associations/${associationId}/logo`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      })
    ).data;
  },
};

// ── LoanType catalogue (config-v2) ────────────────────────────────────────
export const loanTypesApi = {
  list: async (associationId: string, activeOnly = false) =>
    (await api.get("/loan-types", {
      params: { association_id: associationId, active_only: activeOnly },
    })).data,
  create: async (payload: {
    association_id: string;
    source_caisse_id: string;
    name: string;
    slug: string;
    description?: string;
    eligibility_min_seniority_months?: number;
    eligibility_no_default?: boolean;
    max_simultaneous?: number;
    max_per_year?: number;
    interest_rate_pct?: string;
    late_fee_pct?: string;
    max_duration_months?: number;
  }) => (await api.post("/loan-types", payload)).data,
  update: async (id: string, payload: Record<string, unknown>) =>
    (await api.patch(`/loan-types/${id}`, payload)).data,
  remove: async (id: string) => (await api.delete(`/loan-types/${id}`)).data,
};

// ── AidType catalogue (config-v2) ─────────────────────────────────────────
export const aidTypesApi = {
  list: async (associationId: string, activeOnly = false) =>
    (await api.get("/aid-types", {
      params: { association_id: associationId, active_only: activeOnly },
    })).data,
  create: async (payload: {
    association_id: string;
    source_caisse_id: string;
    name: string;
    slug: string;
    description?: string;
    member_contribution_amount?: number;
    is_contribution_recurring?: boolean;
    aid_ceiling_amount?: number;
    max_claims_per_member_per_year?: number;
    declaration_delay_days?: number;
  }) => (await api.post("/aid-types", payload)).data,
  update: async (id: string, payload: Record<string, unknown>) =>
    (await api.patch(`/aid-types/${id}`, payload)).data,
  remove: async (id: string) => (await api.delete(`/aid-types/${id}`)).data,
};

// ── Caisses (config-v2 user-facing wrapper around Fund) ───────────────────
export const caissesApi = {
  list: async (associationId: string, includeInactive = false) =>
    (await api.get("/caisses", {
      params: { association_id: associationId, include_inactive: includeInactive },
    })).data,
  get: async (id: string) => (await api.get(`/caisses/${id}`)).data,
  create: async (payload: {
    association_id: string;
    name: string;
    slug: string;
    description?: string;
    category: "collective" | "project" | "personal";
    is_recurring?: boolean;
    recurring_amount?: number;
    is_member_required?: boolean;
    member_required_amount?: number;
    has_ceiling?: boolean;
    ceiling_amount?: number;
    has_objective?: boolean;
    objective_amount?: number;
    objective_deadline?: string;
  }) => (await api.post("/caisses", payload)).data,
  update: async (id: string, payload: Record<string, unknown>) =>
    (await api.patch(`/caisses/${id}`, payload)).data,
  remove: async (id: string) => (await api.delete(`/caisses/${id}`)).data,
};

export const meetingsApi = {
  list: async (params?: { association_id?: string; status?: string }) =>
    (await api.get("/meetings", { params })).data,
  get: async (id: string) => (await api.get(`/meetings/${id}`)).data,
  create: async (payload: Record<string, unknown>) => (await api.post("/meetings", payload)).data,
  update: async (id: string, payload: Record<string, unknown>) =>
    (await api.patch(`/meetings/${id}`, payload)).data,
  open: async (id: string) => (await api.post(`/meetings/${id}/open`, {})).data,
  close: async (id: string) => (await api.post(`/meetings/${id}/close`, {})).data,
  listAttendances: async (id: string) => (await api.get(`/meetings/${id}/attendances`)).data,
  upsertAttendances: async (id: string, items: Array<{ membership_id: string; status: string; notes?: string }>) =>
    (await api.put(`/meetings/${id}/attendances`, items)).data,
  listEntries: async (id: string, params?: { membership_id?: string }) =>
    (await api.get(`/meetings/${id}/entries`, { params })).data,
  addEntry: async (id: string, payload: Record<string, unknown>) =>
    (await api.post(`/meetings/${id}/entries`, payload)).data,
  updateEntry: async (id: string, entryId: string, payload: Record<string, unknown>) =>
    (await api.patch(`/meetings/${id}/entries/${entryId}`, payload)).data,
  voidEntry: async (id: string, entryId: string) =>
    (await api.delete(`/meetings/${id}/entries/${entryId}`)).data,
  /** Bulk-save one member's whole meeting record (collapse-close flow). */
  saveMember: async (
    id: string,
    payload: {
      membership_id: string;
      attendance?: string;
      attendance_notes?: string;
      excuse_reason?: string;
      entries: Array<{ activity_id: string; amount: number; notes?: string }>;
    },
  ) => (await api.post(`/meetings/${id}/member-save`, payload)).data,
  /** Phase 3b — per-member agenda computed from config-v2 (tontines, caisses,
   *  aids, loans) for this specific meeting. */
  agenda: async (meetingId: string) =>
    (await api.get(`/meetings/${meetingId}/agenda`)).data,
  /** Phase 4 — annuler une séance individuelle.
   *  Si la séance hébergeait un tour de tontine, il est ré-attaché à la
   *  prochaine séance planifiée. */
  cancel: async (meetingId: string) =>
    (await api.post(`/meetings/${meetingId}/cancel`)).data,
};

export const activitiesApi = {
  list: async (params?: { association_id?: string; active_only?: boolean }) =>
    (await api.get("/activities", { params })).data,
  create: async (payload: Record<string, unknown>) => (await api.post("/activities", payload)).data,
  update: async (id: string, payload: Record<string, unknown>) =>
    (await api.patch(`/activities/${id}`, payload)).data,
};


export const membersApi = {
  list: async (associationId: string) =>
    (await api.get("/memberships", { params: { association_id: associationId } })).data,
  create: async (payload: {
    association_id: string;
    email?: string;
    user_id?: string;
    full_name?: string;
    role_codes?: string[];
    member_number?: string;
    notes?: string;
  }) => (await api.post("/memberships", payload)).data,
  update: async (id: string, payload: Record<string, unknown>) =>
    (await api.patch(`/memberships/${id}`, payload)).data,
  remove: async (id: string) => (await api.delete(`/memberships/${id}`)).data,
};

export const tontinesApi = {
  // Liste des tontines (durables) de l'asso, avec résumé du cycle courant.
  list: async (associationId: string) =>
    (await api.get("/tontines", { params: { association_id: associationId } })).data,
  // Détail tontine : config + cycles + cycle courant (avec ses tours).
  get: async (id: string) => (await api.get(`/tontines/${id}`)).data,
  /** Phase 6A — crée la tontine + son 1er cycle + ses séances d'office. */
  create: async (payload: {
    association_id: string;
    name: string;
    description?: string;
    round_amount: number;
    frequency: string; // weekly|biweekly|monthly|bimonthly|custom
    custom_interval_days?: number;
    beneficiaries_per_round?: number;
    beneficiary_pays?: boolean;
    selection_method?: string; // manual|random|seniority|vote|auction|need
    start_date: string;
    is_mandatory?: boolean;
    /** Participants dans l'ordre de passage. Peut être vide : la tontine est
     *  créée en brouillon, les membres sont ajoutés ensuite via sa config. */
    participant_ids: string[];
    excluded_membership_ids?: string[];
    shuffle?: boolean;
  }) => (await api.post("/tontines", payload)).data,
  /** Phase 6A — génère le cycle suivant (hérite tout). */
  createNextCycle: async (tontineId: string, payload?: { start_date?: string }) =>
    (await api.post(`/tontines/${tontineId}/cycles`, payload ?? {})).data,
  /** Définit/édite les participants d'un cycle BROUILLON (régénère ses tours). */
  setParticipants: async (
    cycleId: string,
    payload: {
      participant_ids: string[];
      excluded_membership_ids?: string[];
      is_mandatory?: boolean;
      shuffle?: boolean;
      start_date?: string;
    },
  ) => (await api.put(`/tontines/cycles/${cycleId}/participants`, payload)).data,
  /** Démarre un cycle brouillon (le 1er tour passe en collecte). */
  activateCycle: async (cycleId: string) =>
    (await api.post(`/tontines/cycles/${cycleId}/activate`, {})).data,
  payout: async (cycleId: string, roundId: string) =>
    (await api.post(`/tontines/cycles/${cycleId}/rounds/${roundId}/payout`, {})).data,
  cancelCycle: async (cycleId: string) =>
    (await api.post(`/tontines/cycles/${cycleId}/cancel`, {})).data,
  relinkRound: async (cycleId: string, roundId: string, meetingId: string) =>
    (await api.patch(`/tontines/cycles/${cycleId}/rounds/${roundId}/meeting`, null, {
      params: { meeting_id: meetingId },
    })).data,
};

export const financeApi = {
  treasury: async (associationId: string) =>
    (await api.get("/finance/treasury", { params: { association_id: associationId } })).data,
  movements: async (
    associationId: string,
    params?: { fund_id?: string; direction?: string },
  ) =>
    (await api.get("/finance/movements", { params: { association_id: associationId, ...params } }))
      .data,
  createMovement: async (payload: {
    association_id: string;
    direction: string;
    amount: number;
    fund_id: string;
    to_fund_id?: string;
    occurred_on: string;
    description?: string;
  }) => (await api.post("/finance/movements", payload)).data,
  voidMovement: async (id: string, reason: string) =>
    (await api.post(`/finance/movements/${id}/void`, { reason })).data,
};

export interface AidContribution {
  entry_id: string;
  meeting_id: string;
  meeting_title: string;
  meeting_date: string;
  membership_id: string;
  member_name?: string | null;
  aid_type_id?: string | null;
  aid_type_name?: string | null;
  amount: number;
  status: string;
}

export const socialAidApi = {
  list: async (associationId: string, status?: string) =>
    (await api.get("/social-aid", { params: { association_id: associationId, status } })).data,
  get: async (id: string) => (await api.get(`/social-aid/${id}`)).data,
  declare: async (payload: {
    association_id: string;
    beneficiary_membership_id: string;
    kind: string;
    title: string;
    description?: string;
    event_date?: string;
  }) => (await api.post("/social-aid", payload)).data,
  approve: async (id: string, approvedAmount?: number) =>
    (await api.post(`/social-aid/${id}/approve`, { approved_amount: approvedAmount })).data,
  reject: async (id: string, reason: string) =>
    (await api.post(`/social-aid/${id}/reject`, { reason })).data,
  payout: async (id: string) => (await api.post(`/social-aid/${id}/payout`, {})).data,
  /** Phase 5 — historique des cotisations. RBAC : un membre simple ne voit
   *  que ses propres cotisations, les bureau/admin voient tout. */
  listContributions: async (
    associationId: string,
    params?: {
      membership_id?: string;
      aid_type_id?: string;
      since?: string;
      until?: string;
    },
  ) =>
    (await api.get("/social-aid/contributions", {
      params: { association_id: associationId, ...params },
    })).data as AidContribution[],
};

export const loansApi = {
  list: async (associationId: string, status?: string) =>
    (await api.get("/loans", { params: { association_id: associationId, status } })).data,
  get: async (id: string) => (await api.get(`/loans/${id}`)).data,
  request: async (payload: {
    association_id: string;
    borrower_membership_id: string;
    principal: number;
    duration_months: number;
    interest_rate_pct: number;
    late_fee_pct?: number;
    purpose?: string;
  }) => (await api.post("/loans", payload)).data,
  approve: async (id: string) => (await api.post(`/loans/${id}/approve`, {})).data,
  reject: async (id: string, reason: string) =>
    (await api.post(`/loans/${id}/reject`, { reason })).data,
  disburse: async (id: string) => (await api.post(`/loans/${id}/disburse`, {})).data,
  repay: async (id: string, amount: number) =>
    (await api.post(`/loans/${id}/repay`, { amount })).data,
};
