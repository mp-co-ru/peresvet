import pytest

from src.services.dataStorages.app.integrational.dataStorages_app_integrational_utils import (
    OperationKind,
    ensure_columns_xyq,
    rewrite_named_params,
    validate_sql,
)


def test_validate_sql_rejects_ddl_and_multistatement():
    validate_sql("select 1", OperationKind.GET)
    validate_sql("insert into t(x) values (1)", OperationKind.SET)
    with pytest.raises(ValueError):
        validate_sql("", OperationKind.GET)
    with pytest.raises(ValueError):
        validate_sql("select 1; drop table t", OperationKind.GET)
    with pytest.raises(ValueError):
        validate_sql("create table t(id int)", OperationKind.GET)
    with pytest.raises(ValueError):
        validate_sql("comment on table t is 'x'", OperationKind.GET)


def test_rewrite_named_params_and_xyq():
    sql, names = rewrite_named_params("select * from t where id = :id and x > :start and id = :id")
    assert names == ["id", "start"]
    assert "$1" in sql and "$2" in sql
    sql2, names2 = rewrite_named_params("select 1::int")
    assert names2 == []
    assert "::int" in sql2
    ensure_columns_xyq(["X", "Y", "Q"])
    with pytest.raises(ValueError):
        ensure_columns_xyq(["x", "y"])
