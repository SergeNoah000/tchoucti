import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { PermissionCode, RoleCode, UUID } from "../types";

export interface UserRole {
  code: RoleCode;
  association_id: UUID | null; // null = groupement-level
  permissions: PermissionCode[];
}

interface PermissionState {
  rolesByAssociation: Record<string, UserRole[]>; // key: associationId | "_groupement"
  currentAssociationId: UUID | null;
  isPlatformAdmin: boolean;
  isGroupementAdmin: boolean;
  hasHydrated: boolean;

  setRoles: (associationId: string | null, roles: UserRole[]) => void;
  setCurrentAssociation: (id: UUID | null) => void;
  setPlatformAdmin: (v: boolean) => void;
  setGroupementAdmin: (v: boolean) => void;
  clear: () => void;

  hasPermission: (p: PermissionCode, associationId?: UUID) => boolean;
  hasAnyPermission: (perms: PermissionCode[], associationId?: UUID) => boolean;
  hasRole: (role: RoleCode, associationId?: UUID) => boolean;
}

const GROUPEMENT_KEY = "_groupement";

export const usePermissionStore = create<PermissionState>()(
  persist(
    (set, get) => ({
      rolesByAssociation: {},
      currentAssociationId: null,
      isPlatformAdmin: false,
      isGroupementAdmin: false,
      hasHydrated: false,

      setRoles: (associationId, roles) => {
        const key = associationId ?? GROUPEMENT_KEY;
        set((s) => ({ rolesByAssociation: { ...s.rolesByAssociation, [key]: roles } }));
      },

      setCurrentAssociation: (id) => set({ currentAssociationId: id }),
      setPlatformAdmin: (v) => set({ isPlatformAdmin: v }),
      setGroupementAdmin: (v) => set({ isGroupementAdmin: v }),

      clear: () =>
        set({
          rolesByAssociation: {},
          currentAssociationId: null,
          isPlatformAdmin: false,
          isGroupementAdmin: false,
        }),

      hasPermission: (p, associationId) => {
        const s = get();
        if (s.isPlatformAdmin || s.isGroupementAdmin) return true;
        const target = associationId ?? s.currentAssociationId;
        // Check association-scoped roles
        if (target) {
          const roles = s.rolesByAssociation[target] || [];
          if (roles.some((r) => r.permissions.includes(p))) return true;
        }
        // Check groupement-level roles (admin etc.)
        const groupRoles = s.rolesByAssociation[GROUPEMENT_KEY] || [];
        return groupRoles.some((r) => r.permissions.includes(p));
      },

      hasAnyPermission: (perms, associationId) => {
        const s = get();
        if (s.isPlatformAdmin || s.isGroupementAdmin) return true;
        return perms.some((p) => s.hasPermission(p, associationId));
      },

      hasRole: (role, associationId) => {
        const s = get();
        if (s.isPlatformAdmin && role === "super_admin") return true;
        const target = associationId ?? s.currentAssociationId;
        if (!target) {
          const groupRoles = s.rolesByAssociation[GROUPEMENT_KEY] || [];
          return groupRoles.some((r) => r.code === role);
        }
        const roles = s.rolesByAssociation[target] || [];
        return roles.some((r) => r.code === role);
      },
    }),
    {
      name: "permission-storage",
      partialize: (s) => ({
        rolesByAssociation: s.rolesByAssociation,
        currentAssociationId: s.currentAssociationId,
        isPlatformAdmin: s.isPlatformAdmin,
        isGroupementAdmin: s.isGroupementAdmin,
      }),
      onRehydrateStorage: () => (state) => {
        if (state) state.hasHydrated = true;
      },
    }
  )
);
