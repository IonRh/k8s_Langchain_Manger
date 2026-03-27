import sys
from k8s_tools.self_heal.self_heal_agent import DEFAULT_RULES_PATH, run_self_heal


def main():
    rules_path = DEFAULT_RULES_PATH
    if len(sys.argv) > 1:
        rules_path = sys.argv[1]
    run_self_heal(rules_path)


if __name__ == "__main__":
    main()
