"""KB-058 admin-only on-prem appliance template bundle."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import require_roles

router = APIRouter(tags=["admin-appliances"])

ON_PREM_TEMPLATE_ROLES = ("platform_admin", "soc_manager")

README_TEXT = """# MSSP On-Prem Appliance Template

This bundle is a safe starting template. Replace every angle-bracket placeholder
before deployment. Never commit activation tokens or appliance API keys.

1. Ask a platform administrator for a one-time activation token.
2. Copy `docker-compose.yml.template` to `docker-compose.yml` on the appliance.
3. Replace `<APPLIANCE_IMAGE>`, `<CONTROL_PLANE_URL>`, `<ACTIVATION_TOKEN>`,
   `<APPLIANCE_NAME>`, and `<AGENT_VERSION>`.
4. Start the appliance and confirm registration in the admin Appliances page.
5. Store the returned durable appliance API key in a local secret store; do not
   place it in Git or send it to the customer portal.

The appliance sends normalized metadata only. Raw events, IP addresses,
credentials, packet captures, and internal notes must stay local.
"""

COMPOSE_TEMPLATE_TEXT = """services:
  mssp-on-prem-appliance:
    image: "<APPLIANCE_IMAGE>"
    restart: unless-stopped
    environment:
      CONTROL_PLANE_URL: "<CONTROL_PLANE_URL>"
      APPLIANCE_ACTIVATION_TOKEN: "<ACTIVATION_TOKEN>"
      APPLIANCE_NAME: "<APPLIANCE_NAME>"
      AGENT_VERSION: "<AGENT_VERSION>"
    volumes:
      - appliance_state:/var/lib/mssp-appliance
    read_only: true
    security_opt:
      - no-new-privileges:true

volumes:
  appliance_state:
"""


class TemplateFile(BaseModel):
    path: str
    media_type: str
    content: str


class OnPremTemplateBundle(BaseModel):
    bundle_name: str
    version: str
    files: List[TemplateFile]
    contains_secrets: bool


@router.get(
    "/admin/appliances/on-prem-template",
    response_model=OnPremTemplateBundle,
)
def get_on_prem_template(
    _current_user: Dict[str, Any] = Depends(require_roles(*ON_PREM_TEMPLATE_ROLES)),
) -> Dict[str, Any]:
    return {
        "bundle_name": "mssp-on-prem-appliance-template",
        "version": "kb058-v1",
        "contains_secrets": False,
        "files": [
            {
                "path": "README.md",
                "media_type": "text/markdown",
                "content": README_TEXT,
            },
            {
                "path": "docker-compose.yml.template",
                "media_type": "application/yaml",
                "content": COMPOSE_TEMPLATE_TEXT,
            },
        ],
    }
