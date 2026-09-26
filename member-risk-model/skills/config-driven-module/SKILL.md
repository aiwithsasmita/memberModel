---
name: config-driven-module
description: Use when adding a capability to any stage (source, feature, selection method, model, monitor): add a registry entry and a plugin instead of changing the pipeline.
---

# Extend a stage through its registry

Each stage has a registry in `config/` and a `src/plugins/` folder:

| Stage | Registry | Plugin |
| --- | --- | --- |
| 01_feature_creation | sources.yaml | connector per source |
| 02_feature_engineering | features.yaml | one file per feature group |
| 03_feature_selection | selection.yaml | one file per method |
| 04_model_training | models.yaml | one class per algorithm |
| 08_aiops | monitors.yaml | one check per monitor |

Steps:
1. Add the registry entry with `enabled: true`, owner and the spec FR IDs it implements.
2. Add the plugin file using the stage's `src/plugins/_template.py`.
3. Add tests (unit + leakage where relevant).
4. Do not edit `src/run.py` or the pipeline; they discover plugins from the registry.
5. If the stage's output columns change, update `contract.yaml` and tell the owners of downstream stages.
