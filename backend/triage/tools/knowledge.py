"""Knowledge-base tool: search the project's uploaded documents, URLs and notes."""


from workflows import Context

from .. import runtime
from ..state import get_state


async def search_knowledge(ctx: Context, query: str) -> str:
    """Search the project's knowledge base (uploaded documents, URLs, notes).

    Use this for product context: architecture notes, requirements, known
    limitations, release notes. Returns the most relevant passages with the
    document they came from.
    """
    rt = runtime.for_state(await get_state(ctx))
    if rt.knowledge_empty():
        return "The project knowledge base is empty."
    nodes = await rt.search_knowledge(query)
    if not nodes:
        return "No relevant passages found."
    out = [f"{len(nodes)} passages:"]
    for n in nodes:
        out.append(f"- [{n.metadata.get('name', '?')}] (score={n.score or 0:.2f}) {n.get_content().replace(chr(10), ' ')[:400]}")
    return "\n".join(out)
