# Refactoring Plan for `domain` Package

## Overview
Apply SOLID, DRY, and KISS principles to improve maintainability, testability, and clarity of the `src/domain` package.

## Steps

### 1. Shared Utilities (`src/domain/shared`)
- Deduplicate `event_emitter` usage; ensure a single source.
- Create `helpers.py` facade re‑exporting common helpers (logger, scheduler, feedback).
- Define abstract interfaces `IFeedback`, `ILogger` and depend on them.

### 2. Input Layer (`src/domain/input`)
- Split each module into **adapter** (raw → normalized event) and **mapper** (event → command).
- Extract debounce/repeat logic into a shared utility.
- Keep `__init__.py` minimal, exposing only public facades.

### 3. Shell / UI (`src/domain/shell`)
- Apply MVVM separation: Model (`*_state.py`), ViewModel (`*_view.py`), Controller (`*_control.py`).
- Consolidate session logic into one `session.py` using collaborators via an interface.
- Introduce `OverlayManager` responsible for overlay lifecycle.

### 4. Catalog (`src/domain/catalog`)
- Implement Repository pattern (`CatalogRepository`) for querying.
- Separate rule definition (`rules/`) from rule application (`RuleEngine`).
- Split domain model from UI view‑model (pure entities vs. DTOs).

### 5. Lifecycle (`src/domain/lifecycle`)
- Base class `LifecycleComponent` with template methods `start/stop/restart`.
- Separate launch and hide concerns into distinct modules.
- Centralize prompt dialogs in a shared service (`IPromptService`).

### 6. Navigation (`src/domain/navigation`)
- Create geometry helpers in `shared`.
- Introduce `NavigationStore` holding focus/mode state.
- Define `INavigationStrategy` for keyboard/gamepad/touch and delegate.

### 7. System (`src/domain/system`)
- Wrap OS interactions behind interfaces (`ISystemRunner`, `IActionExecutor`, `IDesktopShell`).
- Extract `ConfigurableTrait` base for getters/setters.
- Separate action definition from UI representation.

### 8. Provisioning (`src/domain/provisioning`)
- Split `provisioning.py` into services: `PortAllocator`, `CatalogResolver`, `SelectionEngine`.
- Facade `ProvisioningFacade` orchestrates them.
- Share candidate validation logic in a stateless validator.

### 9. Notifications (`src/domain/notifications`)
- Extract time/urgency helpers to `notification_utils`.
- Depend on `ISource` interface; register sources via a registry.
- Separate model, renderer, and animator.

## General Refactor Practices
1. Detect duplicated code (`grep -r`, IDE tools) → move to `shared`.
2. Extract interfaces for classes with multiple implementations.
3. Split large files (>200 lines or >2 responsibilities) into focused modules.
4. Prefer composition over inheritance; use constructor injection.
5. Keep `__init__.py` exports minimal; prefix privates with `_`.
6. Write a test for each new utility/interface before removing old code.
7. Run linters/type‑checkers after each change.

## Expected Benefits
- **SOLID**: Clear responsibilities, extensibility via abstractions, dependency inversion.
- **DRY**: Single source of truth for utilities and common logic.
- **KISS**: Short, focused files; obvious data flow; easier onboarding.

--- 

*Plan written by Assistant.*