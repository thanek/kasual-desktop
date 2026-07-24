#!/bin/bash
# One entry point for the behavioral suite. `prepare` in one terminal, `run` in
# another (see tests/behavioral/README.md).
set -euo pipefail
cd "$(dirname "$0")"

usage() {
    cat >&2 <<'EOF'
Usage:
  tests_behav.sh prepare [--seed|--empty|--dir P]   seed a throwaway config and
                                                    launch KD with the test API on
                                                    (defaults to --seed; blocks)
  tests_behav.sh run [ARGS...]                       run the scenarios; ARGS pass
                                                    straight to run.py (a name,
                                                    --list, ...)
EOF
}

cmd="${1:-}"
shift || true

case "$cmd" in
    prepare)
        export_line="$(python3 tests/behavioral/prepare_config.py "${@:---seed}")" || exit 1
        eval "$export_line"
        export KD_TEST_API=1
        exec ./kasual.sh
        ;;
    run)
        exec python3 tests/behavioral/run.py --notify "$@"
        ;;
    *)
        usage
        exit 2
        ;;
esac
