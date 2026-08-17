/** Deterministic dashboard payloads for @mocked chart rendering tests. */

export const MOCK_ADMIN_DASHBOARD = {
  overview: {
    total_tenants: 2,
    total_alerts: 42,
    high_or_critical_alerts: 5,
    open_incidents: 3,
    online_appliances: 2,
    offline_appliances: 0,
  },
  severity_breakdown: [
    { severity: "critical", count: 2 },
    { severity: "high", count: 3 },
    { severity: "medium", count: 10 },
    { severity: "low", count: 27 },
  ],
};

export const MOCK_ADMIN_INCIDENTS = {
  incidents: [
    {
      id: "11111111-1111-1111-1111-111111111111",
      tenant_name: "Alpha-Win-Corp",
      short_code: "ALPHAWINCORP-6VS2",
      incident_number: "INC-ALPHA-MOCK-0001",
      title: "Mock critical incident",
      severity: "critical",
      status: "open",
      opened_at: new Date(Date.now() - 2 * 3600_000).toISOString(),
      created_at: new Date(Date.now() - 2 * 3600_000).toISOString(),
    },
    {
      id: "22222222-2222-2222-2222-222222222222",
      tenant_name: "Alpha-Win-Corp",
      short_code: "ALPHAWINCORP-6VS2",
      incident_number: "INC-ALPHA-MOCK-0002",
      title: "Mock high incident",
      severity: "high",
      status: "open",
      opened_at: new Date(Date.now() - 5 * 3600_000).toISOString(),
      created_at: new Date(Date.now() - 5 * 3600_000).toISOString(),
    },
  ],
  total: 2,
  page: 1,
  page_size: 25,
  total_pages: 1,
  has_next: false,
  has_prev: false,
};

export const MOCK_ADMIN_TENANTS = {
  tenants: [
    {
      id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      name: "Alpha-Win-Corp",
      short_code: "ALPHAWINCORP-6VS2",
      status: "active",
    },
    {
      id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      name: "Beta-Win-Corp",
      short_code: "BETAWINCORP-J3FW",
      status: "active",
    },
  ],
  total: 2,
  page: 1,
  page_size: 200,
  total_pages: 1,
  has_next: false,
  has_prev: false,
};

const now = () => new Date().toISOString();
const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString();

/** Customer portal builds the dashboard client-side from several list APIs. */
export function mockCustomerListBundle(shortCode: string) {
  const tenant = {
    id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
    name: "Alpha-Win-Corp",
    short_code: shortCode,
  };
  return {
    incidents: {
      tenant,
      incidents: [
        {
          id: "i1",
          incident_number: "INC-MOCK-0001",
          title: "Mock open case",
          severity: "critical",
          status: "open",
          opened_at: hoursAgo(1),
          customer_visible_summary: "SOC is investigating a critical case.",
        },
        {
          id: "i2",
          incident_number: "INC-MOCK-0002",
          title: "Mock high case",
          severity: "high",
          status: "open",
          opened_at: hoursAgo(3),
          customer_visible_summary: "Follow-up in progress.",
        },
      ],
      total: 2,
      page: 1,
      page_size: 5,
      total_pages: 1,
      has_next: false,
      has_prev: false,
    },
    alerts: {
      tenant,
      alerts: [
        {
          id: "a1",
          alert_title: "Mock high alert",
          severity: "high",
          status: "new",
          created_at: now(),
          ai_plain_summary: "Unusual activity detected.",
        },
        {
          id: "a2",
          alert_title: "Mock critical alert",
          severity: "critical",
          status: "new",
          created_at: now(),
          ai_plain_summary: "Urgent attention needed.",
        },
        {
          id: "a3",
          alert_title: "Mock medium alert",
          severity: "medium",
          status: "triaged",
          created_at: hoursAgo(2),
          ai_plain_summary: "Reviewed by SOC.",
        },
        {
          id: "a4",
          alert_title: "Mock low alert",
          severity: "low",
          status: "closed",
          created_at: hoursAgo(6),
          ai_plain_summary: "Informational.",
        },
      ],
      total: 4,
      page: 1,
      page_size: 5,
      total_pages: 1,
      has_next: false,
      has_prev: false,
    },
    recommendations: {
      tenant,
      recommendations: [
        {
          id: "r1",
          title: "Patch critical package",
          priority: "high",
          status: "open",
          created_at: now(),
        },
        {
          id: "r2",
          title: "Review MFA coverage",
          priority: "medium",
          status: "in_progress",
          created_at: hoursAgo(4),
        },
        {
          id: "r3",
          title: "Rotate service account",
          priority: "low",
          status: "open",
          created_at: hoursAgo(8),
        },
      ],
      total: 3,
      page: 1,
      page_size: 5,
      total_pages: 1,
      has_next: false,
      has_prev: false,
    },
    assets: {
      tenant,
      assets: [{ id: "as1", hostname: "mock-host", status: "active" }],
      appliances: [{ id: "ap1", appliance_name: "mock-edge", status: "online" }],
      total: 6,
      page: 1,
      page_size: 1,
      total_pages: 6,
      has_next: true,
      has_prev: false,
    },
    reports: {
      tenant,
      reports: [],
      total: 0,
      page: 1,
      page_size: 5,
      total_pages: 0,
      has_next: false,
      has_prev: false,
    },
  };
}
