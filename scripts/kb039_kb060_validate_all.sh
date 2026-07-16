#!/usr/bin/env bash
# KB-039 through KB-060: Run all module validation scripts in sequence.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

SCRIPTS=(
  kb039_validate_deployment_automation_foundation.sh
  kb040_validate_wazuh_stack_vm_deployment_plan.sh
  kb041_validate_wazuh_stack_installation_validation.sh
  kb042_validate_wazuh_agent_onboarding.sh
  kb043_validate_suricata_sensor_deployment_plan.sh
  kb044_validate_suricata_wazuh_integration.sh
  kb045_validate_zeek_sensor_deployment_plan.sh
  kb046_validate_zeek_log_integration.sh
  kb047_validate_thehive_deployment_plan.sh
  kb048_validate_shuffle_soar_deployment_plan.sh
  kb049_validate_wazuh_shuffle_thehive_workflow.sh
  kb050_validate_misp_threat_intel_deployment_plan.sh
  kb051_validate_threat_intel_enrichment_workflow.sh
  kb052_validate_greenbone_vulnerability_management_plan.sh
  kb053_validate_vulnerability_recommendation_workflow.sh
  kb054_validate_velociraptor_dfir_deployment_plan.sh
  kb055_validate_dfir_evidence_safety_case_workflow.sh
  kb056_validate_admin_soc_triage_dashboard_enhancements.sh
  kb057_validate_customer_safe_live_soc_data_integration.sh
  kb058_validate_on_prem_appliance_template_registration.sh
  kb059_validate_multi_cluster_capacity_customer_placement.sh
  kb060_validate_backup_monitoring_upgrade_operations_runbook.sh
)

echo "======================================================================"
echo "KB-039 through KB-060: Master validation runner"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

FAILED=0
for script in "${SCRIPTS[@]}"; do
  path="scripts/$script"
  if [ ! -x "$path" ]; then
    echo "FAIL: missing or not executable: $path" >&2
    FAILED=1
    continue
  fi
  echo
  echo ">>> Running $path"
  if "$path"; then
    echo ">>> OK: $script"
  else
    echo ">>> FAIL: $script" >&2
    FAILED=1
  fi
done

echo
if [ "$FAILED" -ne 0 ]; then
  echo "KB-039 through KB-060 MASTER VALIDATION FAILED" >&2
  exit 1
fi

echo "======================================================================"
echo "KB-039 THROUGH KB-060 MASTER VALIDATION PASSED"
echo "======================================================================"
