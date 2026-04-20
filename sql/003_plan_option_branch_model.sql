-- Plan option branching model upgrade
--
-- 目标：
-- 1. 把 plan_option 从“可复制版本”升级成“带父子关系的方案分支”。
-- 2. 保留 source_plan_option_id 作为兼容字段，但业务主语义转到
--    parent_plan_option_id / branch_root_option_id / branch_name。

ALTER TABLE plan_options
    ADD COLUMN IF NOT EXISTS parent_plan_option_id UUID REFERENCES plan_options(id) ON DELETE SET NULL;

ALTER TABLE plan_options
    ADD COLUMN IF NOT EXISTS branch_root_option_id UUID REFERENCES plan_options(id) ON DELETE SET NULL;

ALTER TABLE plan_options
    ADD COLUMN IF NOT EXISTS branch_name VARCHAR(120);

UPDATE plan_options
SET
    parent_plan_option_id = COALESCE(parent_plan_option_id, source_plan_option_id),
    branch_name = COALESCE(branch_name, title)
WHERE parent_plan_option_id IS NULL
   OR branch_name IS NULL;

WITH RECURSIVE branch_chain AS (
    SELECT
        id,
        parent_plan_option_id,
        id AS root_id
    FROM plan_options
    WHERE parent_plan_option_id IS NULL

    UNION ALL

    SELECT
        child.id,
        child.parent_plan_option_id,
        parent.root_id
    FROM plan_options child
    JOIN branch_chain parent
      ON child.parent_plan_option_id = parent.id
)
UPDATE plan_options AS target
SET branch_root_option_id = branch_chain.root_id
FROM branch_chain
WHERE target.id = branch_chain.id
  AND target.branch_root_option_id IS NULL;

UPDATE plan_options
SET branch_root_option_id = id
WHERE branch_root_option_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_plan_options_parent_plan_option_id
    ON plan_options(parent_plan_option_id);

CREATE INDEX IF NOT EXISTS idx_plan_options_branch_root_option_id
    ON plan_options(branch_root_option_id);
