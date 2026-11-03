import { test, expect, type Page } from "@playwright/test";

// These workflow assertions intentionally exercise the Chinese locale.
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!localStorage.getItem("okr-language"))
      localStorage.setItem("okr-language", "zh-CN");
  });
});

// Browser-only contract fixtures, never served by the application backend.
async function mockWorkspace(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = {};
    if (path === "/api/v1/me")
      data = {
        id: 1,
        name: "测试负责人",
        role: "Manager",
        org_id: 1,
        csrf: "fixture",
      };
    if (path === "/api/v1/catalog")
      data = {
        cycles: [
          {
            id: 1,
            name: "2026 Q4",
            start_date: "2026-10-01",
            end_date: "2026-12-31",
          },
        ],
        users: [],
        org_units: [],
      };
    if (path === "/api/v1/dashboards/executive")
      data = {
        total: 0,
        effective_count: 0,
        achievement: null,
        health: { Green: 0, Amber: 0, Red: 0, Gray: 0 },
        statuses: { Active: 0, Completed: 0 },
        themes: [],
        attention: [],
        as_of: "2026-10-30T01:00:00",
      };
    if (path === "/api/v1/objectives") data = { items: [], total: 0, page: 1 };
    if (
      path === "/api/v1/notifications" ||
      path === "/api/v1/approvals" ||
      path === "/api/v1/review-meetings" ||
      path === "/api/v1/audit-events" ||
      path === "/api/v1/change-requests" ||
      path === "/api/v1/exports"
    )
      data = [];
    if (path === "/api/v1/alignment") data = { nodes: [], edges: [] };
    if (path === "/api/v1/initiatives" || path === "/api/v1/benefits")
      data = [];
    if (path === "/api/v1/dashboards/portfolio")
      data = {
        initiative_count: 0,
        completed_count: 0,
        effort_hours: "0",
        investment: [],
        verified_benefits: [],
        qualitative: [],
      };
    await route.fulfill({ json: data });
  });
}

test("unavailable database leaves login disabled with a clear explanation", async ({
  page,
}) => {
  await page.route("**/auth/config", (route) =>
    route.fulfill({ json: { development_login: false } }),
  );
  await page.route("**/api/status", (route) =>
    route.fulfill({ status: 503, json: { message: "SQL Server尚未配置" } }),
  );
  await page.goto("/login");
  await expect(page.getByText("服务尚未就绪", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Microsoft/ })).toBeDisabled();
  await page.screenshot({ path: "../test-results/login.png", fullPage: true });
});

test("password login handles errors and opens the workspace", async ({
  page,
}) => {
  await mockWorkspace(page);
  await page.route("**/auth/config", (route) =>
    route.fulfill({ json: { password_login: true, development_login: false } }),
  );
  await page.route("**/api/status", (route) =>
    route.fulfill({ json: { status: "ready" } }),
  );
  let attempts = 0;
  await page.route("**/auth/password/login", (route) => {
    attempts++;
    expect(route.request().postDataJSON().username).toBe("employee");
    return route.fulfill(
      attempts === 1
        ? { status: 401, json: { message: "账号或密码错误" } }
        : { json: { ok: true } },
    );
  });
  await page.goto("/login");
  await page.getByRole("button", { name: "登录工作空间" }).click();
  await expect(page.getByRole("alert")).toContainText("请输入账号");
  await page
    .getByRole("textbox", { name: "账号", exact: true })
    .fill("employee");
  await page
    .getByRole("textbox", { name: "密码", exact: true })
    .fill("incorrect");
  await page.getByRole("button", { name: "登录工作空间" }).click();
  await expect(page.getByText("账号或密码错误", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "密码", exact: true }),
  ).toHaveValue("");
  await page
    .getByRole("textbox", { name: "密码", exact: true })
    .fill("a-long-test-password");
  await page.getByRole("textbox", { name: "密码", exact: true }).press("Enter");
  await expect(page.getByRole("heading", { name: "工作总览" })).toBeVisible();
});

test("language switching translates approvals, persists, and preserves form input", async ({
  page,
}) => {
  await mockWorkspace(page);
  await page.goto("/approvals");
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(
    page.getByRole("heading", { name: "Approvals", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("My pending approvals", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("No objectives awaiting approval", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Approvals", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../test-results/approvals-en.png",
    fullPage: true,
  });
  for (const title of [
    "Strategic alignment",
    "Reviews & actions",
    "Initiatives & benefits",
    "Audit trail",
  ]) {
    await page.getByRole("link", { name: title, exact: true }).click();
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
  }
  await page.getByRole("link", { name: "Objectives & key results" }).click();
  await page
    .getByRole("button", { name: "Create objective", exact: true })
    .click();
  await page
    .getByPlaceholder(
      "e.g. Improve operational efficiency and free up time for innovation",
    )
    .fill("保留用户原文");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("button", { name: "中文", exact: true }).click();
  await page.getByRole("button", { name: "创建目标", exact: true }).click();
  await expect(
    page.getByPlaceholder("例如：提升运营效率，释放团队创新时间"),
  ).toHaveValue("保留用户原文");
  await expect(page.getByRole("dialog", { name: "创建目标" })).toBeVisible();
});

test("login page supports English and Chinese", async ({ page }) => {
  await page.route("**/auth/config", (route) =>
    route.fulfill({ json: { password_login: true, development_login: false } }),
  );
  await page.route("**/api/status", (route) =>
    route.fulfill({ json: { status: "ready" } }),
  );
  await page.goto("/login");
  await page
    .getByRole("textbox", { name: "账号", exact: true })
    .fill("employee");
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Username", exact: true }),
  ).toHaveValue("employee");
  await page.getByRole("button", { name: "Sign in →", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Enter your password");
  await page.screenshot({
    path: "../test-results/login-en.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "中文", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "欢迎进入工作空间" }),
  ).toBeVisible();
});

test("English mobile navigation and workspace fit the viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockWorkspace(page);
  await page.goto("/approvals");
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Approvals", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../test-results/mobile-en.png",
    fullPage: true,
  });
});

test("workspace navigation, empty states and objective form", async ({
  page,
}) => {
  await mockWorkspace(page);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "工作总览" })).toBeVisible();
  await expect(
    page.getByText("创建目标后，战略主题将在这里呈现"),
  ).toBeVisible();
  await page.screenshot({
    path: "../test-results/workspace.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "目标与关键结果" }).click();
  await expect(
    page.getByRole("heading", { name: "目标与关键结果" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "创建目标", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "创建目标" })).toBeVisible();
  await page
    .getByPlaceholder("例如：提升运营效率，释放团队创新时间")
    .fill("测试目标");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  for (const title of [
    "战略对齐",
    "审批中心",
    "评审与行动",
    "举措与收益",
    "审计记录",
  ]) {
    await page.getByRole("link", { name: title }).click();
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test("alignment uses objective cards and distinguishes all relationship types", async ({
  page,
}) => {
  await mockWorkspace(page);
  const nodes = [
    {
      id: 1,
      title: "Digital transformation",
      level: "corporate",
      status: "Active",
      org_id: 1,
      org_name: "Bank strategy",
      owner_name: "Alex Lee",
      progress: "62",
      kr_count: 1,
      key_results: [
        { id: 11, name: "Digital adoption", progress: "62", health: "Green" },
      ],
    },
    {
      id: 2,
      title: "Technology delivery",
      level: "division",
      status: "Active",
      org_id: 1,
      org_name: "Technology",
      owner_name: "Jamie Chan",
      progress: "55",
      kr_count: 1,
      key_results: [
        { id: 12, name: "Release outcomes", progress: "55", health: "Amber" },
      ],
    },
    {
      id: 3,
      title: "Operational efficiency",
      level: "department",
      status: "Active",
      org_id: 2,
      org_name: "Operations",
      owner_name: "Sam Wong",
      progress: "73",
      kr_count: 1,
      key_results: [
        {
          id: 13,
          name: "Save processing hours",
          progress: "73",
          health: "Green",
        },
      ],
    },
    {
      id: 4,
      title: "Strengthen controls",
      level: "department",
      status: "Active",
      org_id: 3,
      org_name: "Risk",
      owner_name: "Chris Ho",
      progress: "41",
      kr_count: 1,
      key_results: [
        {
          id: 14,
          name: "Reduce control exceptions",
          progress: "41",
          health: "Red",
        },
      ],
    },
    {
      id: 5,
      title: "Automate service requests",
      level: "team",
      status: "Active",
      org_id: 2,
      org_name: "Operations",
      owner_name: "Morgan Lam",
      progress: "68",
      kr_count: 1,
      key_results: [
        {
          id: 15,
          name: "Automated workflows",
          progress: "68",
          health: "Green",
        },
      ],
    },
  ];
  await page.route("**/api/v1/alignment*", (route) =>
    route.fulfill({
      json: {
        nodes,
        edges: [
          { source: 2, target: 1, kind: "parent" },
          { source: 3, target: 2, kind: "parent" },
          { source: 4, target: 2, kind: "parent" },
          { source: 5, target: 3, kind: "parent" },
          { source: 4, target: 1, kind: "contributes_to" },
          { source: 5, target: 1, kind: "contributes_to" },
          { source: 3, target: 4, kind: "depends_on" },
        ],
      },
    }),
  );
  await page.goto("/alignment");
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(page.locator(".alignment-card")).toHaveCount(5);
  await expect(page.locator("path.alignment-wire.parent")).toHaveCount(4);
  await expect(page.locator("path.alignment-wire.contributes_to")).toHaveCount(
    2,
  );
  await expect(page.locator("path.alignment-wire.depends_on")).toHaveCount(1);
  await expect(
    page.locator(".alignment-card").filter({ hasText: "Alex Lee" }),
  ).toContainText("62%");
  await page.locator(".alignment-card").filter({ hasText: "Sam Wong" }).click();
  await expect(page.locator(".alignment-card.dimmed")).toHaveCount(1);
  await page
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  await page.locator(".alignment-legend .el-checkbox").nth(1).click();
  await expect(page.locator("path.alignment-wire.contributes_to")).toHaveCount(
    0,
  );
  await page.locator(".alignment-legend .el-checkbox").nth(1).click();
  await page.locator(".alignment-legend .el-checkbox").nth(3).click();
  await expect(page.locator("path.alignment-wire.parent")).toHaveCount(2);
  await page.locator(".alignment-legend .el-checkbox").nth(3).click();
  await page.getByRole("button", { name: "Fit width", exact: true }).click();
  await page.screenshot({
    path: "../test-results/alignment-cards.png",
    fullPage: true,
  });
  await page.locator(".alignment-relation-list summary").click();
  await expect(page.locator(".alignment-relation-list")).toContainText(
    "Cross-department: Operations / Risk",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page
    .locator(".alignment-title")
    .filter({ hasText: "Digital transformation" })
    .focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/objectives\/1$/);
});

test("non-admin cannot access people management", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/people");
  await expect(
    page.getByRole("heading", { name: "工作总览", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "人员管理", exact: true }),
  ).toHaveCount(0);
});

test("admin can create, edit, reset passwords and disable people", async ({
  page,
}) => {
  await mockWorkspace(page);
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({
      json: {
        id: 1,
        name: "Administrator",
        role: "System Admin",
        org_id: 1,
        csrf: "fixture",
      },
    }),
  );
  let people: {
    id: number;
    name: string;
    username: string;
    role: string;
    org_id: number;
    org_name: string;
    active: boolean;
    etag: string;
  }[] = [];
  let reset = false;
  await page.route("**/api/v1/admin/people**", (route) => {
    const path = new URL(route.request().url()).pathname,
      method = route.request().method();
    if (path.endsWith("/options"))
      return route.fulfill({
        json: {
          organizations: [{ id: 1, name: "Technology" }],
          roles: ["Employee", "Manager", "System Admin"],
        },
      });
    if (path.endsWith("/people") && method === "GET")
      return route.fulfill({ json: { items: people, total: people.length } });
    const body = route.request().postDataJSON();
    expect(route.request().headers()["x-csrf-token"]).toBe("fixture");
    if (path.endsWith("/people")) {
      expect(body.username).toBe("new.person");
      expect(body.password).toBe("Initial-password-123");
      people = [
        {
          id: 20,
          name: body.name,
          username: body.username,
          role: body.role,
          org_id: 1,
          org_name: "Technology",
          active: true,
          etag: '"v1"',
        },
      ];
      return route.fulfill({ status: 201, json: people[0] });
    }
    expect(route.request().headers()["if-match"]).toBe(people[0].etag);
    if (path.endsWith("/password")) {
      expect(body.password).toBe("Replacement-password-456");
      reset = true;
      return route.fulfill({ json: { ok: true } });
    }
    if (path.endsWith("/active"))
      people[0] = { ...people[0], active: body.active, etag: '"v3"' };
    else people[0] = { ...people[0], ...body, etag: '"v2"' };
    return route.fulfill({ json: people[0] });
  });
  await page.goto("/people");
  await page.getByRole("button", { name: "新增人员", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "新增人员", exact: true });
  await dialog.locator(".el-input__inner").nth(0).fill("New colleague");
  await dialog.locator(".el-input__inner").nth(1).fill("new.person");
  await dialog.locator(".el-select").nth(0).click();
  await page.getByRole("option", { name: "Technology", exact: true }).click();
  await dialog
    .locator('input[type="password"]')
    .nth(0)
    .fill("Initial-password-123");
  await dialog
    .locator('input[type="password"]')
    .nth(1)
    .fill("Initial-password-123");
  await dialog.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(page.getByText("new.person", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  const edit = page.getByRole("dialog", { name: "编辑人员", exact: true });
  await edit.locator(".el-select").nth(1).click();
  await page.getByRole("option", { name: "经理", exact: true }).click();
  await edit.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "经理", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "重设密码", exact: true }).click();
  const pwd = page.getByRole("dialog", { name: "重设密码", exact: true });
  await pwd
    .locator('input[type="password"]')
    .nth(0)
    .fill("Replacement-password-456");
  await pwd
    .locator('input[type="password"]')
    .nth(1)
    .fill("Replacement-password-456");
  await pwd.getByRole("button", { name: "确认重设", exact: true }).click();
  await expect(pwd).not.toBeVisible();
  expect(reset).toBeTruthy();
  await page.getByRole("button", { name: "停用", exact: true }).click();
  await page.getByRole("button", { name: "确认", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "已停用", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "People management", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../test-results/people-management.png",
    fullPage: true,
  });
});

test("organization analytics renders division scores and review risk separately", async ({
  page,
}) => {
  await mockWorkspace(page);
  await page.route("**/api/v1/dashboards/organization*", (route) =>
    route.fulfill({
      json: {
        divisions: [
          {
            id: 1,
            name: "Technology division",
            count: 2,
            achievement: "65.00",
          },
        ],
        departments: [
          {
            id: 2,
            name: "Operations department",
            count: 2,
            achievement: "65.00",
            statuses: { Active: 2 },
            health: { Green: 2, Amber: 1, Red: 1, Gray: 0 },
            overdue_reviews: 3,
            risk_concentration: "50.00",
          },
        ],
        strategic_value: "80.00",
        assessed_count: 1,
        effective_count: 2,
        unplanned_reviews: 1,
        assessments: [
          {
            objective_id: 12,
            score: 80,
            rationale: "Customer service priority",
          },
        ],
      },
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "事业部评分" })).toBeVisible();
  await expect(
    page.getByText("Technology division", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("50.00%", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Customer service priority", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Department analytics" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../test-results/organization-analytics.png",
    fullPage: true,
  });
});

test("quarterly retrospective saves conclusions and preserves the completed record", async ({
  page,
}) => {
  await mockWorkspace(page);
  let completed = false;
  await page.route("**/api/v1/quarterly-reviews*", (route) =>
    route.fulfill({
      json: [
        {
          id: 7,
          objective_id: 12,
          objective_title: "Quarterly delivery",
          reviewer_id: 1,
          reviewer: "Reviewer",
          due_date: "2026-10-01",
          status: completed ? "Completed" : "Pending",
          overdue: !completed,
          summary: completed ? "Reviewed outcome" : "",
          lessons: completed ? "Improve measurement" : "",
          next_steps: completed ? "Next quarter plan" : "",
        },
      ],
    }),
  );
  await page.route("**/api/v1/quarterly-reviews/7/complete", (route) => {
    expect(route.request().postDataJSON()).toEqual({
      summary: "Reviewed outcome",
      lessons: "Improve measurement",
      next_steps: "Next quarter plan",
    });
    completed = true;
    return route.fulfill({ json: { ok: true } });
  });
  await page.goto("/reviews");
  await expect(page.getByText("已逾期", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "完成复盘", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "完成复盘" });
  for (const [i, text] of [
    "Reviewed outcome",
    "Improve measurement",
    "Next quarter plan",
  ].entries())
    await dialog.locator("textarea").nth(i).fill(text);
  await dialog.getByRole("button", { name: "保存记录", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "完成复盘", exact: true }),
  ).toHaveCount(0);
  await page
    .locator("summary")
    .filter({ hasText: "Quarterly delivery" })
    .click();
  await expect(
    page.getByText("复盘结论: Reviewed outcome", { exact: true }),
  ).toBeVisible();
});

test("active KR update submits precision-safe values and concurrency token", async ({
  page,
}) => {
  await mockWorkspace(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const objective = {
    id: 101,
    code: "TEST-101",
    title: "提升运营效率",
    description: "浏览器契约测试目标",
    owner_id: 1,
    owner_name: "测试负责人",
    org_id: 1,
    org_name: "技术部",
    cycle_id: 1,
    theme: "运营效率",
    priority: "High",
    level: "department",
    visibility: "organization",
    start_date: "2026-10-01",
    end_date: "2026-12-31",
    status: "Active",
    revision: 1,
    etag: '"fixture-objective"',
    kr_count: 1,
    progress: "25.00",
    health_counts: { Green: 1, Amber: 0, Red: 0, Gray: 0 },
    approvals: [],
    evidence: [],
    key_results: [
      {
        id: 202,
        name: "节约处理工时",
        value_type: "number",
        direction: "increase",
        baseline: "0.0000",
        current_value: "25.0000",
        target: "100.0000",
        weight: "100.0000",
        unit: "小时",
        frequency: "monthly",
        confidence: 80,
        progress: "25.00",
        raw_progress: "25.00",
        health: "Green",
        next_due: "2026-11-01",
        etag: '"fixture-kr"',
        milestones: [],
      },
    ],
  };
  await page.route("**/api/v1/objectives/101", (route) =>
    route.fulfill({ json: objective }),
  );
  await page.route("**/api/v1/key-results/202/check-ins", async (route) => {
    if (route.request().method() === "POST") {
      const payload = route.request().postDataJSON();
      expect(payload.current_value).toBe("50.1250");
      expect(payload.commentary).toBe("根据已核对的工时记录更新");
      expect(route.request().headers()["if-match"]).toBe('"fixture-kr"');
      expect(route.request().headers()["x-csrf-token"]).toBe("fixture");
      objective.key_results[0].current_value = payload.current_value;
      objective.key_results[0].progress = "50.13";
      await route.fulfill({
        status: 201,
        json: { check_in_id: 1, ...objective.key_results[0] },
      });
    } else await route.fulfill({ json: [] });
  });
  await page.route("**/api/v1/change-requests?objective_id=101", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/objectives/101/snapshots", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.goto("/objectives/101");
  await expect(
    page.getByRole("heading", { name: "提升运营效率" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "更新进展", exact: true }).click();
  await page.getByLabel("当前值", { exact: true }).fill("50.1250");
  await page
    .getByLabel("进展说明", { exact: true })
    .fill("根据已核对的工时记录更新");
  await page.getByRole("button", { name: "提交更新", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "更新关键结果" })).toBeHidden();
  await expect(page.getByText("50.13%", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "变更与权限" }).click();
  await expect(page.getByRole("button", { name: "申请变更" })).toBeVisible();
  await page.getByRole("button", { name: "申请变更" }).click();
  await expect(
    page.getByRole("dialog", { name: "申请变更目标定义" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect(errors).toEqual([]);
});

test("benefits keep claimed, verified and qualitative results separate", async ({
  page,
}) => {
  await mockWorkspace(page);
  await page.route("**/api/v1/dashboards/portfolio*", (route) =>
    route.fulfill({
      json: {
        initiative_count: 2,
        completed_count: 1,
        effort_hours: "80.0000",
        investment: [{ currency: "CNY", value: "10000.0000" }],
        verified_benefits: [
          { category: "cost_saving", unit: "CNY", value: "8000.0000" },
          { category: "hours_saved", unit: "小时", value: "120.0000" },
        ],
        qualitative: [
          {
            id: 1,
            name: "操作风险控制完善",
            category: "risk_reduction",
            value: null,
            unit: "等级",
          },
        ],
      },
    }),
  );
  await page.goto("/portfolio");
  await expect(page.getByRole("heading", { name: "举措与收益" })).toBeVisible();
  await expect(page.getByText("风险与合规改善", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "收益申报与核验" }).click();
  await expect(
    page.getByRole("button", { name: "登记收益", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../test-results/portfolio.png",
    fullPage: true,
  });
});

test("narrow viewport remains usable", async ({ page }) => {
  await mockWorkspace(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "工作总览" })).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  expect(overflow).toBe(false);
  await page.screenshot({ path: "../test-results/mobile.png", fullPage: true });
});
