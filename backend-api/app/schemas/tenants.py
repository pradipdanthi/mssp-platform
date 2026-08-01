"""
KB-013: Request/response models for the /admin/tenants/* management
endpoints (GET one, POST, PATCH).

KB-073: deployment_mode + cloud_provider for customer onboarding path.
KB-074: customer organization profile (contact + address fields).
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

StatusLiteral = Literal["onboarding", "active", "inactive", "suspended"]
SlaLevelLiteral = Literal["standard", "business", "premium", "24x7"]
CriticalityLiteral = Literal["low", "medium", "high", "critical"]
DeploymentModeLiteral = Literal[
    "cloud",
    "cloud_appliance",
    "on_prem_direct",
    "on_prem_appliance",
    "hybrid",
]
CloudProviderLiteral = Literal["aws", "azure", "gcp", "other"]

_CLOUD_PROVIDER_REQUIRED_MODES = frozenset({"cloud", "cloud_appliance"})
_CLOUD_PROVIDER_ALLOWED_MODES = frozenset({"cloud", "cloud_appliance", "hybrid"})

_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

PROFILE_OPTIONAL_FIELDS = (
    "primary_contact_phone",
    "secondary_contact_name",
    "secondary_contact_email",
    "secondary_contact_phone",
    "billing_email",
    "address_line1",
    "address_line2",
    "city",
    "state_region",
    "postal_code",
    "website",
    "industry",
    "legal_name",
    "tax_id",
    "contract_reference",
    "data_residency",
    "preferred_language",
    "company_size",
)

COMMERCIAL_DATE_FIELDS = ("contract_start_date", "contract_end_date")

# Core-only onboarding defaults (add-ons AVAILABLE until consulting approved).
# Alpha-Win demo short code is forced to full catalog in create_tenant.
DEFAULT_CREATE_ENTITLEMENTS = {
    "wazuh_siem": True,
    "wazuh_retention_days": 90,
    "thehive_mode": "full",
    "greenbone_enabled": False,
    "greenbone_cadence": "monthly",
    "shuffle_mode": "off",
    "zeek_enabled": False,
    "misp_enabled": False,
    "velociraptor_enabled": False,
    "continuous_compliance_enabled": False,
    "external_attack_surface_enabled": False,
    "cloud_identity_protection_enabled": False,
    "roadmap_notes": None,
}


def _normalize_cloud_provider(
    deployment_mode: str,
    cloud_provider: Optional[str],
) -> Optional[str]:
    if deployment_mode in _CLOUD_PROVIDER_REQUIRED_MODES:
        if not cloud_provider:
            raise ValueError(
                "cloud_provider is required when deployment_mode is cloud or cloud_appliance"
            )
        return cloud_provider
    if deployment_mode == "hybrid":
        return cloud_provider
    # On-prem paths: provider not applicable
    return None


def mode_allows_cloud_provider(deployment_mode: str) -> bool:
    return deployment_mode in _CLOUD_PROVIDER_ALLOWED_MODES


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    return text or None


class EntitlementsOnCreate(BaseModel):
    """Contracted services selected during Add Customer (KB-075)."""

    wazuh_siem: bool = True
    wazuh_retention_days: int = Field(default=90, ge=30, le=365)
    thehive_mode: Literal["full", "read_only", "off"] = "full"
    greenbone_enabled: bool = False
    greenbone_cadence: Literal["weekly", "monthly", "off"] = "monthly"
    shuffle_mode: Literal["standard", "custom", "off"] = "off"
    zeek_enabled: bool = False
    misp_enabled: bool = False
    velociraptor_enabled: bool = False
    continuous_compliance_enabled: bool = False
    external_attack_surface_enabled: bool = False
    cloud_identity_protection_enabled: bool = False
    roadmap_notes: Optional[str] = Field(default=None, max_length=2000)


class PortalAdminOnCreate(BaseModel):
    """Optional first customer portal admin created with the tenant."""

    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL_RE)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    phone: Optional[str] = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def normalize(self) -> "PortalAdminOnCreate":
        self.email = self.email.strip().lower()
        self.full_name = self.full_name.strip()
        self.phone = _blank_to_none(self.phone)
        return self


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    short_code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    status: StatusLiteral = "active"
    sla_level: SlaLevelLiteral = "standard"
    business_criticality: CriticalityLiteral = "medium"
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    notes: Optional[str] = None
    deployment_mode: DeploymentModeLiteral = "cloud"
    cloud_provider: Optional[CloudProviderLiteral] = None

    # KB-074 profile — required for new customers
    primary_contact_name: str = Field(min_length=1, max_length=200)
    primary_contact_email: str = Field(min_length=3, max_length=320, pattern=_EMAIL_RE)
    country: str = Field(min_length=2, max_length=100)

    primary_contact_phone: Optional[str] = Field(default=None, max_length=40)
    secondary_contact_name: Optional[str] = Field(default=None, max_length=200)
    secondary_contact_email: Optional[str] = Field(default=None, max_length=320)
    secondary_contact_phone: Optional[str] = Field(default=None, max_length=40)
    billing_email: Optional[str] = Field(default=None, max_length=320)
    address_line1: Optional[str] = Field(default=None, max_length=300)
    address_line2: Optional[str] = Field(default=None, max_length=300)
    city: Optional[str] = Field(default=None, max_length=120)
    state_region: Optional[str] = Field(default=None, max_length=120)
    postal_code: Optional[str] = Field(default=None, max_length=32)
    website: Optional[str] = Field(default=None, max_length=300)
    industry: Optional[str] = Field(default=None, max_length=120)

    # KB-075 commercial / contract
    legal_name: Optional[str] = Field(default=None, max_length=200)
    tax_id: Optional[str] = Field(default=None, max_length=64)
    contract_reference: Optional[str] = Field(default=None, max_length=120)
    contract_start_date: Optional[str] = Field(default=None, max_length=10)
    contract_end_date: Optional[str] = Field(default=None, max_length=10)
    licensed_endpoints: Optional[int] = Field(default=None, ge=1, le=1000000)
    data_residency: Optional[str] = Field(default=None, max_length=80)
    preferred_language: Optional[str] = Field(default="en", max_length=16)
    company_size: Optional[str] = Field(default=None, max_length=40)

    entitlements: Optional[EntitlementsOnCreate] = None
    # Required: every new customer gets a portal admin at onboard time (KB-075).
    portal_admin: PortalAdminOnCreate

    @field_validator(
        "secondary_contact_email",
        "billing_email",
        mode="before",
    )
    @classmethod
    def optional_email_or_empty(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return value

    @field_validator("secondary_contact_email", "billing_email")
    @classmethod
    def validate_optional_emails(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        import re

        if not re.match(_EMAIL_RE, value.strip()):
            raise ValueError("Invalid email address")
        return value.strip()

    @field_validator("contract_start_date", "contract_end_date", mode="before")
    @classmethod
    def empty_date_to_none(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return value

    @field_validator("contract_start_date", "contract_end_date")
    @classmethod
    def validate_iso_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        import re

        text = value.strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            raise ValueError("Dates must be YYYY-MM-DD")
        return text

    @model_validator(mode="after")
    def normalize_fields(self) -> "TenantCreateRequest":
        self.short_code = self.short_code.strip().upper()
        self.cloud_provider = _normalize_cloud_provider(
            self.deployment_mode, self.cloud_provider
        )
        self.primary_contact_name = self.primary_contact_name.strip()
        self.primary_contact_email = self.primary_contact_email.strip().lower()
        self.country = self.country.strip()
        for field_name in PROFILE_OPTIONAL_FIELDS:
            setattr(self, field_name, _blank_to_none(getattr(self, field_name)))
        if self.secondary_contact_email:
            self.secondary_contact_email = self.secondary_contact_email.lower()
        if self.billing_email:
            self.billing_email = self.billing_email.lower()
        self.notes = _blank_to_none(self.notes)
        if self.preferred_language:
            self.preferred_language = self.preferred_language.strip().lower()
        if (
            self.contract_start_date
            and self.contract_end_date
            and self.contract_end_date < self.contract_start_date
        ):
            raise ValueError("contract_end_date must be on or after contract_start_date")
        return self


class TenantUpdateRequest(BaseModel):
    """
    All fields optional (PATCH semantics) - at least one must be provided.
    short_code is intentionally not updatable.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[StatusLiteral] = None
    sla_level: Optional[SlaLevelLiteral] = None
    business_criticality: Optional[CriticalityLiteral] = None
    timezone: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None
    deployment_mode: Optional[DeploymentModeLiteral] = None
    cloud_provider: Optional[CloudProviderLiteral] = None

    primary_contact_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    primary_contact_email: Optional[str] = Field(
        default=None, min_length=3, max_length=320, pattern=_EMAIL_RE
    )
    primary_contact_phone: Optional[str] = Field(default=None, max_length=40)
    secondary_contact_name: Optional[str] = Field(default=None, max_length=200)
    secondary_contact_email: Optional[str] = Field(default=None, max_length=320)
    secondary_contact_phone: Optional[str] = Field(default=None, max_length=40)
    billing_email: Optional[str] = Field(default=None, max_length=320)
    address_line1: Optional[str] = Field(default=None, max_length=300)
    address_line2: Optional[str] = Field(default=None, max_length=300)
    city: Optional[str] = Field(default=None, max_length=120)
    state_region: Optional[str] = Field(default=None, max_length=120)
    postal_code: Optional[str] = Field(default=None, max_length=32)
    country: Optional[str] = Field(default=None, min_length=2, max_length=100)
    website: Optional[str] = Field(default=None, max_length=300)
    industry: Optional[str] = Field(default=None, max_length=120)

    legal_name: Optional[str] = Field(default=None, max_length=200)
    tax_id: Optional[str] = Field(default=None, max_length=64)
    contract_reference: Optional[str] = Field(default=None, max_length=120)
    contract_start_date: Optional[str] = Field(default=None, max_length=10)
    contract_end_date: Optional[str] = Field(default=None, max_length=10)
    licensed_endpoints: Optional[int] = Field(default=None, ge=1, le=1000000)
    data_residency: Optional[str] = Field(default=None, max_length=80)
    preferred_language: Optional[str] = Field(default=None, max_length=16)
    company_size: Optional[str] = Field(default=None, max_length=40)

    @field_validator(
        "secondary_contact_email",
        "billing_email",
        mode="before",
    )
    @classmethod
    def optional_email_or_empty(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return value

    @field_validator("secondary_contact_email", "billing_email")
    @classmethod
    def validate_optional_emails(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        import re

        if not re.match(_EMAIL_RE, value.strip()):
            raise ValueError("Invalid email address")
        return value.strip().lower()

    @field_validator("contract_start_date", "contract_end_date", mode="before")
    @classmethod
    def empty_date_to_none(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return value

    @field_validator("contract_start_date", "contract_end_date")
    @classmethod
    def validate_iso_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        import re

        text = str(value).strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            raise ValueError("Dates must be YYYY-MM-DD")
        return text

    @model_validator(mode="after")
    def at_least_one_field(self) -> "TenantUpdateRequest":
        if all(v is None for v in self.__dict__.values()):
            raise ValueError("At least one field must be provided")
        if self.primary_contact_email:
            self.primary_contact_email = self.primary_contact_email.strip().lower()
        if self.primary_contact_name:
            self.primary_contact_name = self.primary_contact_name.strip()
        if self.country:
            self.country = self.country.strip()
        for field_name in PROFILE_OPTIONAL_FIELDS:
            if field_name in self.model_fields_set:
                setattr(self, field_name, _blank_to_none(getattr(self, field_name)))
        if "notes" in self.model_fields_set:
            self.notes = _blank_to_none(self.notes)
        if (
            self.contract_start_date
            and self.contract_end_date
            and self.contract_end_date < self.contract_start_date
        ):
            raise ValueError("contract_end_date must be on or after contract_start_date")
        return self


class OnboardResult(BaseModel):
    entitlements_saved: bool = False
    portal_user_created: bool = False
    portal_user_email: Optional[str] = None
    portal_user_error: Optional[str] = None
    service_readiness: Dict[str, str] = Field(default_factory=dict)
    next_steps: List[str] = Field(default_factory=list)


class TenantDetail(BaseModel):
    id: str
    name: str
    short_code: str
    status: str
    sla_level: str
    business_criticality: str
    timezone: str
    notes: Optional[str] = None
    deployment_mode: str
    cloud_provider: Optional[str] = None
    primary_contact_name: Optional[str] = None
    primary_contact_email: Optional[str] = None
    primary_contact_phone: Optional[str] = None
    secondary_contact_name: Optional[str] = None
    secondary_contact_email: Optional[str] = None
    secondary_contact_phone: Optional[str] = None
    billing_email: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state_region: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None
    contract_reference: Optional[str] = None
    contract_start_date: Optional[str] = None
    contract_end_date: Optional[str] = None
    licensed_endpoints: Optional[int] = None
    data_residency: Optional[str] = None
    preferred_language: Optional[str] = None
    company_size: Optional[str] = None
    created_at: str
    updated_at: str
    appliances: int
    protected_assets: int
    incidents: int
    engine_binding: Optional[dict] = None
    entitlements: Optional[dict] = None
    onboard_result: Optional[OnboardResult] = None


class TenantEngineBinding(BaseModel):
    tenant_id: str
    wazuh_agent_group: str
    wazuh_group_status: str
    wazuh_last_error: Optional[str] = None
    wazuh_provisioned_at: Optional[str] = None
    thehive_org_name: str
    thehive_tenant_tag: str
    thehive_org_status: str
    thehive_last_error: Optional[str] = None
    thehive_provisioned_at: Optional[str] = None
    last_provision_attempt_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
