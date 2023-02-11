import asyncio
from io import BytesIO

import magic

from modules.util.executor import executor


@executor()
def detect_content_type(buffer: BytesIO) -> str:
    return magic.from_buffer(buffer)


async def execute(command: str, verbose: bool = False) -> str:
    proc = await asyncio.wait_for(
        asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=None if verbose else asyncio.subprocess.PIPE,
        ),
        timeout=60,
    )

    stdout, _ = await proc.communicate()

    return stdout.decode()
