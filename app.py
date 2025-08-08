import argparse
from colorama import Fore, Style, init as colorama_init
from src.agent.agent import ChatAgent


def main():
    parser = argparse.ArgumentParser(description="Local Chat Agent (Ollama/Azure) with Web Search")
    parser.add_argument("--no-web", action="store_true", help="Disable any web search/fetching")
    parser.add_argument("--verbose", action="store_true", help="Show agent thinking steps (planning/search)")
    args = parser.parse_args()

    colorama_init(autoreset=True)
    def thinker(msg: str) -> None:
        print(Fore.MAGENTA + "[think] " + Style.RESET_ALL + msg)

    agent = ChatAgent(allow_web=not args.no_web, verbose=args.verbose, printer=thinker)

    print(Fore.GREEN + "Local Agent ready. Type your question. Type /exit to quit.")
    print(Fore.GREEN + "Tips: /web <q> to force search; /ctx to list cached sources; /summarize <q> to answer using cached pages.")
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

        # Force web search command
        if user.lower().startswith("/web ") or user.lower().startswith("/search "):
            q = user.split(" ", 1)[1].strip()
            if not q:
                print(Fore.YELLOW + "Agent:" + Style.RESET_ALL, "Please provide a query after /web")
                continue
            reply = agent.handle_query(q, force_web=True)
            print(Fore.YELLOW + "Agent:" + Style.RESET_ALL, reply)
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
            print(Fore.YELLOW + "Agent:" + Style.RESET_ALL, reply)
            continue

        reply = agent.handle_query(user)
        print(Fore.YELLOW + "Agent:" + Style.RESET_ALL, reply)


if __name__ == "__main__":
    main()
