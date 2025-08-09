import argparse
from colorama import Fore, Style, init as colorama_init
from src.agent.agent import ChatAgent
from src.agent.action_agent import ActionAgent
from src.agent.orchestrator import Orchestrator
from src.agent.memory import ConversationMemory


def main():
    parser = argparse.ArgumentParser(description="Local Chat Agent (Ollama/Azure) with Web Search")
    parser.add_argument("--no-web", action="store_true", help="Disable any web search/fetching")
    parser.add_argument("--verbose", action="store_true", help="Show agent thinking steps (planning/search)")
    args = parser.parse_args()

    colorama_init(autoreset=True)
    def thinker(msg: str) -> None:
        print(Fore.MAGENTA + "[think] " + Style.RESET_ALL + msg)

    # Initialize memory before passing it into the ChatAgent
    memory = ConversationMemory(max_messages=30)
    agent = ChatAgent(allow_web=not args.no_web, verbose=args.verbose, printer=thinker, memory=memory)

    print(Fore.GREEN + "Local Agent ready. Type your question. Type /exit to quit.")
    print(Fore.GREEN + "Tips: /web <q> force search; /ctx list cached sources; /summarize <q> summarize cached pages; /task <goal> run autonomous task.")
    
    router = Orchestrator()
    while True:
        try:
            user = input(Fore.CYAN + "You: " + Style.RESET_ALL).strip()
        except (KeyboardInterrupt, EOFError):
            print()  # newline
            break

        if not user:
            continue
        if user.lower() in {"/exit", "exit", "quit", ":q"}:
            break

        # Show recent history
        if user.lower().strip() == "/history":
            print(Fore.MAGENTA + memory.as_bullets(10) + Style.RESET_ALL)
            continue

        # Force web search command
        if user.lower().startswith("/web ") or user.lower().startswith("/search "):
            q = user.split(" ", 1)[1].strip()
            if not q:
                print(Fore.YELLOW + "Agent:" + Style.RESET_ALL, "Please provide a query after /web")
                continue
            reply = agent.handle_query(q, force_web=True)
            memory.add_user(user)
            print(Fore.YELLOW + "Agent:" + Style.RESET_ALL, reply)
            memory.add_assistant(reply)
            continue

        # Show cached context
        if user.lower().strip() == "/ctx":
            pages = getattr(agent, "_last_context_pages", [])
            if not pages:
                print(Fore.YELLOW + "Agent:" + Style.RESET_ALL, "Cache is empty. Use /web to perform a search.")
            else:
                for i, p in enumerate(pages, 1):
                    print(Fore.MAGENTA + f"[{i}]" + Style.RESET_ALL, p.get("title") or "(untitled)")
                    print(" URL:", p.get("url"))
            continue

        # Summarize using cached context
        if user.lower().startswith("/summarize "):
            q = user.split(" ", 1)[1].strip()
            reply = agent.answer_from_last_context(q or "Summarize the sources")
            memory.add_user(user)
            print(Fore.YELLOW + "Agent:" + Style.RESET_ALL, reply)
            memory.add_assistant(reply)
            continue

        # Autonomous action mode
        if user.lower().startswith("/task "):
            goal = user.split(" ", 1)[1].strip()
            if not goal:
                print(Fore.YELLOW + "Agent:" + Style.RESET_ALL, "Please provide a task goal after /task")
                continue
            action = ActionAgent(printer=lambda m: print(Fore.MAGENTA + "[act] " + Style.RESET_ALL + m))
            result = action.run_task(goal)
            print(Fore.YELLOW + "Agent:" + Style.RESET_ALL, result)
            continue

        # LLM-driven orchestration: decide chat vs. action vs. search vs. clarify
        try:
            recent = memory.as_bullets(8)
            routed_input = (f"Context:\n{recent}\n\n{user}" if recent else user)
            decision = router.decide(routed_input)
        except Exception as e:
            # Fallback to normal chat if router fails
            decision = {"need_action": False, "need_search": False, "clarify": None, "goal": "", "reason": f"router_error: {e}"}

        if args.verbose:
            try:
                import json as _json
                thinker("router.decision: " + _json.dumps(decision, ensure_ascii=False))
            except Exception:
                pass

        if decision.get("clarify"):
            print(Fore.YELLOW + "Agent:" + Style.RESET_ALL, decision["clarify"])  # ask the user a question
            memory.add_user(user)
            memory.add_assistant(decision["clarify"])    
            continue

        if decision.get("need_action"):
            goal = decision.get("goal") or user
            print(Fore.YELLOW + "Agent:" + Style.RESET_ALL, "Starting autonomous task execution...")
            action = ActionAgent(printer=lambda m: print(Fore.MAGENTA + "[act] " + Style.RESET_ALL + m), verbose=args.verbose)
            result = action.run_task(goal)
            memory.add_user(user)
            print(Fore.YELLOW + "Agent:" + Style.RESET_ALL, result)
            memory.add_assistant(result)
            continue

        # Pass through to chat agent; if router thinks search is required, we can hint by prefixing /web semantics
        if decision.get("need_search") and agent.allow_web:
            reply = agent.handle_query(user, force_web=True)
        else:
            reply = agent.handle_query(user)
        memory.add_user(user)
        print(Fore.YELLOW + "Agent:" + Style.RESET_ALL, reply)
        memory.add_assistant(reply)


if __name__ == "__main__":
    main()
