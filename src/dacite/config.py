import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

from dacite.frozen_dict import FrozenDict

if sys.version_info.minor >= 8:
    from functools import cached_property  # type: ignore
else:
    # Remove when we drop support for Python<3.8
    cached_property = property  # type: ignore


@dataclass
class Config:
    type_hooks: Dict[Type, Callable[[Any], Any]] = field(default_factory=dict)
    cast: List[Type] = field(default_factory=list)
    forward_references: Optional[Dict[str, Any]] = None
    check_types: bool = True
    strict: bool = False
    strict_unions_match: bool = False

    @cached_property
    def hashable_forward_references(self) -> Optional[FrozenDict]:
        return FrozenDict(self.forward_references) if self.forward_references else None
