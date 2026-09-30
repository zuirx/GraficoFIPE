import duckdb

print('Convertendo CSV para DuckDB...')
conn = duckdb.connect('fipe.duckdb')
conn.execute("CREATE TABLE fipe AS SELECT * FROM read_csv_auto('fipex-prices-latest.csv')")
print('Criando índices...')
conn.execute("CREATE INDEX idx_tipo ON fipe(tipo_veiculo)")
conn.execute("CREATE INDEX idx_marca ON fipe(nome_marca)")
conn.execute("CREATE INDEX idx_modelo ON fipe(nome_modelo)")
print('Pronto! Criado fipe.duckdb')
conn.close()
