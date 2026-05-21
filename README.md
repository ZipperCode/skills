# Shared Claude Skills

这个仓库用于保存可在多端复用的本地 Claude skills。仓库只保存 skill 定义、参考资料、脚本和模板，不保存本机运行配置或真实凭据。

## Included Skills

- `grill-me`
- `herosms-api`
- `sub2api-account-manager`
- `temp-mail`
- `temp-mail-orchestration`

所有 skill 都放在 `skills/<skill-name>/` 下，每个目录保留原始 `SKILL.md` 和必要的 `references/`、`scripts/`、`templates/` 资源。

## Install To Claude

默认安装到 `~/.claude/skills`：

```bash
bash scripts/install.sh
```

如需安装到其他目录：

```bash
CLAUDE_SKILLS_DIR=/path/to/skills bash scripts/install.sh
```

安装脚本会覆盖同名 skill 目录，使目标目录与仓库中的版本保持一致。

## Sync From Local

当本机 `~/.claude/skills` 中的这些 skill 有更新时，可以同步回仓库：

```bash
bash scripts/sync-from-local.sh
```

如需从其他来源同步：

```bash
SOURCE_SKILLS_DIR=/path/to/skills bash scripts/sync-from-local.sh
```

同步脚本只处理白名单中的 5 个 skill，不会自动引入其他本地 skill。

## Notes

- 不提交 `.DS_Store`、`.ace-tool/`、`.serena/` 等本机或工具产物。
- 不提交 `~/.hermes/email/temp-mail.json` 等真实运行配置。
- 提交前建议运行：

```bash
bash -n scripts/install.sh scripts/sync-from-local.sh
find skills -name .DS_Store -print
```
