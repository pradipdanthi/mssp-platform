# Offline package pool (airgap ISO)

For customer sites with no Internet during install, drop `.deb` packages here
(wazuh-manager, fluent-bit, suricata, …). Firstboot / `wazuh_local` will prefer
this pool when present.

Until this directory is populated by CI, firstboot installs engines from
vendor APT repos during the **bootstrap** network window, then leaves them
**disabled** until a Junexis license is applied.
