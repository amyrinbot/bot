import inspect
import re
from typing import Any, Dict
from discord.ext import commands

class InvalidTypeException(Exception):
    pass

class MissingArgument(Exception):
    pass

class MissingFlag(Exception):
    pass

class Required:
    def __init__(self, value: Any) -> None:
        self.value = value

class FlagParser(commands.Converter):
    """basically a commands.FlagConverter but with support for not passing values for bool keys"""
    
    def __init__(self, values: Dict[str, type]) -> None:
        self.values = values
        
        self._regex = r"(?:(?:--([a-zA-Z0-9\-]+))(?: ([a-z0-9]+))?)+"
        
        super().__init__()
        
    async def _probe_type(self, context: commands.Context, name: str, value: Any) -> Any:
        entry = self.values[name]
        
        entry = getattr(entry, "value", entry)
        
        if inspect.isclass(entry) and issubclass(entry, commands.Converter):
            func = entry().convert(context, value)
        else:
            func = entry
            
        try:
            if inspect.iscoroutine(func):
                value = await func
            elif inspect.iscoroutinefunction(func):
                value = await func(value)
            else:
                value = func(value)
        except (commands.BadArgument, ValueError):
            type_ = entry.__name__
            actual = value.__class__.__name__
            raise InvalidTypeException(f"flag \"{name}\" expected type \"{type_}\", got \"{actual}\" instead")
        
        return value
        
    async def _find_matches(self, context: commands.Context, argument: str) -> Dict[str, Any]:
        matches: Dict[str, Any] = {}
        for name, value in re.findall(self._regex, argument):
            if name not in self.values.keys():
                continue
            
            value = getattr(value, "value", value)
            
            if value == "":
                type_ = self.values[name]
                if type_ is not bool:
                    raise MissingArgument(
                        f"argument is required for flag that is not of type \"bool\""
                    )
                    
                matches[name] = True
            else:
                value = await self._probe_type(context, name, value)
                matches[name] = value
            
                
        for name, value in self.values.items():
            if isinstance(value, Required) and name not in matches.keys():
                raise MissingFlag(f"flag \"{name}\" is required but missing")
            elif name not in matches.keys():
                entry = self.values[name]
                if entry is bool:
                    matches[name] = False
                
        
        return matches
                    
                

    async def convert(self, ctx: commands.Context, argument: str) -> Dict[str, Any]:
        return await self._find_matches(ctx, argument)
    
DownloadFlags = FlagParser(
    {
        "format": str,
        "compress": bool,
        "include-tags": bool
    }
)

async def setup(bot):
    pass