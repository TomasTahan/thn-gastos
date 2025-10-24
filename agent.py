from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from rich import print
from rich.console import Console
from cli_tools import parser, print_rich_message, parse_and_print_message
from dotenv import load_dotenv
load_dotenv()



async def main():
    console = Console()
    args = parser.parse_args()

    
    options = ClaudeAgentOptions(
        model=args.model,
        allowed_tools=["Read", "Write"],
        disallowed_tools=["WebSearch", "WebFetch"],
        permission_mode="default",
        setting_sources=["project"],
        settings='{"outputStyle": "personal-assistant"}',
        system_prompt="claude_code",  # Required to load Claude Code's system prompt (including output-styles)
        # add_dirs=["."], # allow access to other directories
    )

    print_rich_message(
        "system",
        f"Welcome to your personal assistant, Kaya!\n\nSelected model: {args.model}",
        console
        )

    async with ClaudeSDKClient(options=options) as client:

        input_prompt = "Hi, what's your name?"
        print_rich_message("user", input_prompt, console)

        await client.query(input_prompt)

        async for message in client.receive_response():
            # Uncomment to print raw messages for debugging
            # print(message)
            parse_and_print_message(message, console)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())