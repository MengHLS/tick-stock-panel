import polars as pl
df = pl.DataFrame({
    "date": ["d1"]*6,
    "symbol": list("abcdef"),
    "x": [10.0, 20.0, 30.0, 40.0, None, 50.0],
    "u": [1.0, 0.0, 1.0, 0.0, 1.0, None],
})
print("version", pl.__version__)
print("--- cast f64->bool")
print(df.with_columns(pl.col("u").cast(pl.Boolean).alias("b")))
print("--- rank average with null")
print(df.with_columns(pl.col("x").rank("average").over("date").alias("rk")))
print("--- mean of masked")
m = pl.when(pl.col("u").cast(pl.Boolean).fill_null(False) & pl.col("x").is_not_null()).then(pl.col("x")).otherwise(None)
print(df.with_columns(m.alias("mx")).with_columns(pl.col("mx").mean().over("date").alias("mu")))
print("--- all-null mean")
m2 = pl.when(pl.lit(False)).then(pl.col("x")).otherwise(None)
print(df.with_columns(m2.alias("mx")).with_columns(pl.col("mx").mean().over("date").alias("mu")))
print("--- bool mean")
b = (pl.col("x") > 25)
print(df.with_columns(b.cast(pl.Float64).alias("bf")).with_columns(pl.col("bf").mean().over("date").alias("m")))
print("--- same-expression rank vs count")
inner = pl.col("x")
print(df.with_columns((inner.rank("average").over("date") / inner.count().over("date")).alias("r")))
