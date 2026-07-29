"""KB-084: Admin download of standardized endpoint onboarding config packages."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.dependencies import require_roles

router = APIRouter(prefix="/admin/onboarding", tags=["admin-onboarding"])

ADMIN_ROLES = ("platform_admin", "soc_manager", "soc_analyst", "customer_admin")

_CONFIG_ROOT_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "endpoint_configs",
    Path("/opt/mssp-control/templates/endpoint-configs"),
    Path("/app/app/endpoint_configs"),
)


def _config_root() -> Path:
    for candidate in _CONFIG_ROOT_CANDIDATES:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("endpoint config templates not found")


def _require_file(root: Path, name: str) -> Path:
    path = root / name
    if not path.is_file():
        raise HTTPException(status_code=500, detail=f"Missing template: {name}")
    return path


@router.get("/agent-configs/{os_type}")
def download_agent_config_package(
    os_type: str,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_ROLES)),
) -> StreamingResponse:
    """
    Return a ZIP with ready-to-deploy endpoint telemetry configs.

    os_type: windows | linux | macos | all
    """
    _ = current_user
    os_key = (os_type or "").strip().lower()
    if os_key not in ("windows", "linux", "macos", "all"):
        raise HTTPException(
            status_code=400,
            detail="os_type must be one of: windows, linux, macos, all",
        )

    try:
        root = _config_root()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Endpoint config templates unavailable")

    agent_params = _require_file(root, "wazuh-agent-parameters.conf")
    readme = root / "README.md"
    sysmon = root / "sysmon-windows-baseline.xml"
    osquery = root / "osquery-endpoint-pack.conf"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if readme.is_file():
            zf.writestr("README.md", readme.read_text(encoding="utf-8"))
        zf.writestr("agent-parameters.conf", agent_params.read_text(encoding="utf-8"))

        if os_key in ("windows", "all"):
            if not sysmon.is_file():
                raise HTTPException(status_code=500, detail="Missing Windows telemetry template")
            zf.writestr(
                "windows/sysmon-windows-baseline.xml",
                sysmon.read_text(encoding="utf-8"),
            )
            zf.writestr(
                "windows/process-telemetry-baseline.xml",
                sysmon.read_text(encoding="utf-8"),
            )
            telemetry_ps1 = root / "Enable-MsspWindowsTelemetry.ps1"
            if telemetry_ps1.is_file():
                zf.writestr(
                    "windows/Enable-MsspWindowsTelemetry.ps1",
                    telemetry_ps1.read_text(encoding="utf-8"),
                )
                zf.writestr(
                    "windows/bootstrap_windows_telemetry.ps1",
                    telemetry_ps1.read_text(encoding="utf-8"),
                )
            zf.writestr(
                "windows/INSTALL.txt",
                (
                    "Already have the endpoint agent enrolled?\n"
                    "1. Copy windows/ folder to the host.\n"
                    "2. Run elevated PowerShell:\n"
                    "     powershell -ExecutionPolicy Bypass -File .\\Enable-MsspWindowsTelemetry.ps1\n"
                    "3. Confirm success line: MSSP_WINDOWS_TELEMETRY_OK\n\n"
                    "New hosts: prefer the per-customer agent ZIP (install-windows-agent.ps1),\n"
                    "which runs this telemetry bootstrap automatically after agent install.\n"
                ),
            )
        if os_key in ("linux", "macos", "all"):
            if not osquery.is_file():
                raise HTTPException(status_code=500, detail="Missing inventory pack template")
            folder = "linux" if os_key != "macos" else "macos"
            if os_key == "all":
                for folder_name in ("linux", "macos"):
                    zf.writestr(
                        f"{folder_name}/endpoint-telemetry-pack.conf",
                        osquery.read_text(encoding="utf-8"),
                    )
                    zf.writestr(
                        f"{folder_name}/INSTALL.txt",
                        (
                            "1. Install the endpoint security agent with agent-parameters.conf.\n"
                            "2. Enable the endpoint telemetry pack "
                            "(process, FIM, network sockets).\n"
                            "3. Confirm process events reach the control plane.\n"
                        ),
                    )
            else:
                zf.writestr(
                    f"{folder}/endpoint-telemetry-pack.conf",
                    osquery.read_text(encoding="utf-8"),
                )
                zf.writestr(
                    f"{folder}/INSTALL.txt",
                    (
                        "1. Install the endpoint security agent with agent-parameters.conf.\n"
                        "2. Enable the endpoint telemetry pack "
                        "(process, FIM, network sockets).\n"
                        "3. Confirm process events reach the control plane.\n"
                    ),
                )

    buf.seek(0)
    filename = f"mssp-endpoint-configs-{os_key}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
