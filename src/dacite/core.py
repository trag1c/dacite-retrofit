import sys
import typing  # noqa: F401, it's there on purpose
from dataclasses import is_dataclass
from itertools import zip_longest
from types import ModuleType
from typing import (  # type: ignore[attr-defined]
    Any,
    Collection,
    ForwardRef,
    Mapping,
    MutableMapping,
    Optional,
    Type,
    TypeVar,
    _allowed_types,
    _eval_type,
)

from future_typing import transform_annotation

from dacite.cache import cache
from dacite.config import Config
from dacite.data import Data
from dacite.dataclasses import (
    DefaultValueNotFoundError,
    get_default_value_for_field,
    get_fields,
    is_frozen,
)
from dacite.exceptions import (
    DaciteError,
    DaciteFieldError,
    ForwardReferenceError,
    MissingValueError,
    StrictUnionMatchError,
    UnexpectedDataError,
    UnionMatchError,
    WrongTypeError,
)
from dacite.types import (
    extract_generic,
    extract_init_var,
    extract_origin_collection,
    is_generic_collection,
    is_init_var,
    is_instance,
    is_optional,
    is_subclass,
    is_union,
)

if sys.version_info < (3, 11):
    from typing import _get_defaults  # type: ignore[attr-defined]
else:

    def _get_defaults(func):
        try:
            code = func.__code__
        except AttributeError:
            return {}
        arg_names = code.co_varnames[: (pos_count := code.co_argcount)]
        res = func.__kwdefaults__.copy()
        pos_offset = pos_count - len(defaults := func.__defaults__ or ())
        for name, value in zip(arg_names[pos_offset:], defaults):
            assert name not in res
            res[name] = value
        return res


T = TypeVar("T")


def resolve_annotations(obj, globalns=None, localns=None):
    # Based on typing.get_type_hints

    if getattr(obj, "__no_type_check__", None):
        return {}
    # Classes require a special treatment.
    if isinstance(obj, type):
        hints = {}
        for base in reversed(obj.__mro__):
            if globalns is None:
                base_globals = sys.modules[base.__module__].__dict__
            else:
                base_globals = globalns
            ann = base.__dict__.get("__annotations__", {})
            for name, val in ann.items():
                value = val
                if value is None:
                    value = type(None)
                if isinstance(value, str):
                    try:
                        value = eval(transform_annotation(value))
                    except NameError:
                        value = ForwardRef(value)
                value = _eval_type(value, base_globals, localns)
                hints[name] = value
        return hints

    if globalns is None:
        if isinstance(obj, ModuleType):
            globalns = obj.__dict__
        else:
            nsobj = obj
            # Find globalns for the unwrapped object.
            while hasattr(nsobj, "__wrapped__"):
                nsobj = nsobj.__wrapped__
            globalns = getattr(nsobj, "__globals__", {})
        if localns is None:
            localns = globalns
    elif localns is None:
        localns = globalns
    hints = getattr(obj, "__annotations__", None)
    if hints is None:
        # Return empty annotations for something that _could_ have them.
        if isinstance(obj, _allowed_types):
            return {}
        raise TypeError(f"{obj!r} is not a module, class, method, or function.")
    defaults = _get_defaults(obj)
    hints = dict(hints)
    for name, val in hints.items():
        value = val
        if value is None:
            value = type(None)
        if isinstance(value, str):
            try:
                value = eval(transform_annotation(value))
            except NameError:
                value = ForwardRef(value)
        value = _eval_type(value, globalns, localns)
        if name in defaults and defaults[name] is None:
            value = Optional[value]
        hints[name] = value
    return hints


def from_dict(data_class: Type[T], data: Data, config: Optional[Config] = None) -> T:
    """Create a data class instance from a dictionary.

    :param data_class: a data class type
    :param data: a dictionary of a input data
    :param config: a configuration of the creation process
    :return: an instance of a data class
    """
    init_values: MutableMapping[str, Any] = {}
    post_init_values: MutableMapping[str, Any] = {}
    config = config or Config()
    try:
        data_class_hints = cache(resolve_annotations)(
            data_class, localns=config.hashable_forward_references
        )
    except NameError as error:
        raise ForwardReferenceError(str(error))
    data_class_fields = cache(get_fields)(data_class)
    if config.strict:
        extra_fields = set(data.keys()) - {f.name for f in data_class_fields}
        if extra_fields:
            raise UnexpectedDataError(keys=extra_fields)
    for field in data_class_fields:
        field_type = data_class_hints[field.name]
        if field.name in data:
            try:
                field_data = data[field.name]
                value = _build_value(type_=field_type, data=field_data, config=config)
            except DaciteFieldError as error:
                error.update_path(field.name)
                raise
            if config.check_types and not is_instance(value, field_type):
                raise WrongTypeError(
                    field_path=field.name, field_type=field_type, value=value
                )
        else:
            try:
                value = get_default_value_for_field(field, field_type)
            except DefaultValueNotFoundError:
                if not field.init:
                    continue
                raise MissingValueError(field.name)
        if field.init:
            init_values[field.name] = value
        elif not is_frozen(data_class):
            post_init_values[field.name] = value
    instance = data_class(**init_values)
    for key, value in post_init_values.items():
        setattr(instance, key, value)
    return instance


def _build_value(type_: Type, data: Any, config: Config) -> Any:
    if is_init_var(type_):
        type_ = extract_init_var(type_)
    if type_ in config.type_hooks:
        data = config.type_hooks[type_](data)
    if is_optional(type_) and data is None:
        return data
    if is_union(type_):
        data = _build_value_for_union(union=type_, data=data, config=config)
    elif is_generic_collection(type_):
        data = _build_value_for_collection(collection=type_, data=data, config=config)
    elif cache(is_dataclass)(type_) and isinstance(data, Mapping):
        data = from_dict(data_class=type_, data=data, config=config)
    for cast_type in config.cast:
        if is_subclass(type_, cast_type):
            if is_generic_collection(type_):
                data = extract_origin_collection(type_)(data)
            else:
                data = type_(data)
            break
    return data


def _build_value_for_union(union: Type, data: Any, config: Config) -> Any:
    types = extract_generic(union)
    if is_optional(union) and len(types) == 2:
        return _build_value(type_=types[0], data=data, config=config)
    union_matches = {}
    for inner_type in types:
        try:
            try:
                value = _build_value(type_=inner_type, data=data, config=config)
            except Exception:
                continue
            if is_instance(value, inner_type):
                if config.strict_unions_match:
                    union_matches[inner_type] = value
                else:
                    return value
        except DaciteError:
            pass
    if config.strict_unions_match:
        if len(union_matches) > 1:
            raise StrictUnionMatchError(union_matches)
        return union_matches.popitem()[1]
    if not config.check_types:
        return data
    raise UnionMatchError(field_type=union, value=data)


def _build_value_for_collection(collection: Type, data: Any, config: Config) -> Any:
    data_type = data.__class__
    if isinstance(data, Mapping) and is_subclass(collection, Mapping):
        item_type = extract_generic(collection, defaults=(Any, Any))[1]
        return data_type(
            (key, _build_value(type_=item_type, data=value, config=config))
            for key, value in data.items()
        )
    elif isinstance(data, tuple) and is_subclass(collection, tuple):
        if not data:
            return data_type()
        types = extract_generic(collection)
        if len(types) == 2 and types[1] == Ellipsis:
            return data_type(
                _build_value(type_=types[0], data=item, config=config) for item in data
            )
        return data_type(
            _build_value(type_=type_, data=item, config=config)
            for item, type_ in zip_longest(data, types)
        )
    elif isinstance(data, Collection) and is_subclass(collection, Collection):
        item_type = extract_generic(collection, defaults=(Any,))[0]
        return data_type(
            _build_value(type_=item_type, data=item, config=config) for item in data
        )
    return data
