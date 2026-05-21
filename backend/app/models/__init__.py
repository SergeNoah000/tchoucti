"""All SQLAlchemy models — must be imported here for Alembic autogenerate."""
from app.models.base import BaseModel, TimestampMixin, UUIDMixin  # noqa: F401

# Tenant & identity
from app.models.groupement import Groupement  # noqa: F401
from app.models.association import Association  # noqa: F401
from app.models.user import User, UserType, InviteStatus  # noqa: F401
from app.models.role import (  # noqa: F401
    Role,
    Permission,
    RolePermission,
    Membership,
    MembershipRole,
    UserPermission,
    RoleScope,
    MembershipStatus,
)

# Finance — core
from app.models.finance import (  # noqa: F401
    Treasury,
    Fund,
    FundKind,
    TreasuryMovement,
    MovementDirection,
    LedgerEntry,
)

# Meetings & activities
from app.models.meeting import (  # noqa: F401
    Meeting,
    MeetingStatus,
    MeetingAttendance,
    AttendanceStatus,
    ActivityType,
    Activity,
    MeetingActivityEntry,
    EntryStatus,
)

# Tontine
from app.models.tontine import (  # noqa: F401
    TontineCycle,
    TontineCycleStatus,
    TontineRound,
    TontineRoundStatus,
    TontineContribution,
)

# Loans
from app.models.loan import (  # noqa: F401
    Loan,
    LoanStatus,
    LoanInstallment,
    LoanInstallmentStatus,
    LoanRepayment,
)

# Social aid
from app.models.social_aid import (  # noqa: F401
    SocialAidCase,
    SocialAidCaseKind,
    SocialAidCaseStatus,
    SocialAidPayout,
)

# Projects
from app.models.project import (  # noqa: F401
    Project,
    ProjectStatus,
    ProjectContribution,
)

# Documents / audit / notifications
from app.models.document import Document, DocumentVisibility  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.notification import Notification, NotificationKind  # noqa: F401

# Invitations + groupement admins
from app.models.invitation import (  # noqa: F401
    Invitation,
    InvitationKind,
    InvitationStatus,
    generate_invitation_token,
)
from app.models.groupement_admin import GroupementAdmin  # noqa: F401
