# Last Handoff

- last_task: `v0.601-aria-label-constraint`
- status: done
- summary: 新增无障碍约束“禁止原生元素裸用 `title` 属性，统一 `aria-label`”，写入 `DESIGN.md` / `PRODUCT.md`；新增前端测试 `frontend/src/utils/noBareTitleAttr.test.ts` 扫描全部 `.vue` 做防回归（PascalCase 组件 `title` prop 豁免）。现有代码已合规，0 违规。
- verify: `cd frontend && npm run test` 通过，59 tests；`cd frontend && npm run build` 通过。
- next_read: `docs/01-ROADMAP.md`
