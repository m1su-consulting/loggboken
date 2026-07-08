from app.errors import ApiError
from app.parsers.base import BaseSourceParser
from app.parsers.kubernetes import KubernetesSourceParser
from app.parsers.rpm import RpmSourceParser

SOURCE_PARSERS: dict[str, BaseSourceParser] = {
    "rpm": RpmSourceParser(),
    "kubernetes": KubernetesSourceParser(),
}


def get_parser(source_type: str) -> BaseSourceParser:
    parser = SOURCE_PARSERS.get(source_type)
    if parser is None:
        raise ApiError(
            status_code=400,
            error="unsupported_source",
            detail=f"okänd source_type '{source_type}', förväntade en av {sorted(SOURCE_PARSERS)}",
        )
    return parser
