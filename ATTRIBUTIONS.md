# Open Source Software Attributions

**Kevantic NikTiar™ MSSP Control Plane & Appliance Platform**

Copyright © Kevantic Cyber Security. All rights reserved.

This repository and the Kevantic NikTiar™ product stack incorporate third-party open-source security, telemetry, and infrastructure components. The notices below acknowledge the original copyright holders and applicable license terms.

Customer-facing portals, marketing pages, and alert panels use **Kevantic NikTiar™** capability branding only. Upstream project names appear in this document and on the appliance filesystem at `/usr/share/doc/kevantic/ATTRIBUTIONS.txt` for legal compliance.

## Branded capability mapping

| Kevantic NikTiar™ capability | Backend execution components (attribution only) |
|---|---|
| NikTiar™ Core Telemetry | Wazuh, Fluent Bit |
| NikTiar™ DeepSight NDR | Suricata, Zeek |
| NikTiar™ Aegis Scanning | Nuclei, Vuls, Greenbone GVM |
| NikTiar™ Apex Orchestrator | TheHive, Shuffle (where deployed) |
| NikTiar™ Spectre Forensics | Velociraptor (where deployed) |

## Disclaimer

THE THIRD-PARTY SOFTWARE LISTED BELOW IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT. IN NO EVENT SHALL THE COPYRIGHT HOLDERS OR CONTRIBUTORS BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT, OR OTHERWISE, ARISING FROM, OUT OF, OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Third-party components

### Wazuh

- **Copyright:** Wazuh Inc.
- **License:** [GNU General Public License v2.0 (GPL-2.0)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html)

### Fluent Bit

- **Copyright:** Fluent Bit authors / Treasure Data, Inc. and contributors
- **License:** [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)

### Suricata

- **Copyright:** OISF (Open Information Security Foundation) and contributors
- **License:** [GNU General Public License v2.0 (GPL-2.0)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html)

### Zeek

- **Copyright:** The Regents of the University of California and contributors
- **License:** [BSD 3-Clause License](https://opensource.org/licenses/BSD-3-Clause)

### Nuclei

- **Copyright:** ProjectDiscovery, Inc.
- **License:** [MIT License](https://opensource.org/licenses/MIT)

### Vuls

- **Copyright:** Future Corporation and contributors
- **License:** [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)

### Greenbone GVM (OpenVAS components)

- **Copyright:** Greenbone AG and contributors
- **License:** [GNU General Public License v3.0 (GPL-3.0)](https://www.gnu.org/licenses/gpl-3.0.html)

### Velociraptor

- **Copyright:** Rapid7 and contributors
- **License:** [GNU Affero General Public License v3.0 (AGPL-3.0)](https://www.gnu.org/licenses/agpl-3.0.html)

## Additional platform dependencies

The control plane (FastAPI, PostgreSQL, Redis, nginx, Docker/Podman, Python packages, and Node.js build tooling) includes numerous additional open-source libraries distributed under MIT, BSD, Apache 2.0, and other permissive licenses. See each component’s upstream repository and `requirements.txt` / `package-lock.json` manifests for complete dependency license metadata.

## Copyleft source availability

Source code for GPL-2.0, GPL-3.0, and AGPL-3.0 components is available from the respective upstream projects. Where license terms require offer of corresponding source with distributed appliances, contact Kevantic Cyber Security support with your tenant identifier and appliance software version.

## Appliance install path

The immutable appliance image bakes this notice at:

```text
/usr/share/doc/kevantic/ATTRIBUTIONS.txt
```

Installed via `kevantic-appliance/mkosi/build.sh` and Ansible role `kevantic_runtime`.
