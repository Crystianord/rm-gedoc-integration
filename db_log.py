import os

import pyodbc
from dotenv import load_dotenv

load_dotenv()

DB_CONNECTION_STRING = (
    "Driver={ODBC Driver 17 for SQL Server};"
    f"Server={os.getenv('DB_SERVER')},{os.getenv('DB_PORT', '1433')};"
    f"Database={os.getenv('DB_DATABASE')};"
    f"UID={os.getenv('DB_USER')};"
    f"PWD={os.getenv('DB_PASSWORD')}"
)

_db_conn = None


def _get_conn():
    global _db_conn
    try:
        if _db_conn is None:
            raise Exception("sem conexão")
        _db_conn.cursor().execute("SELECT 1")
    except Exception:
        _db_conn = pyodbc.connect(DB_CONNECTION_STRING)
    return _db_conn


def init_db():
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='LogIntegracaoGEDOC' AND xtype='U')
        CREATE TABLE LogIntegracaoGEDOC (
            Id       INT IDENTITY(1,1) PRIMARY KEY,
            DataHora DATETIME      NOT NULL,
            CPF      NVARCHAR(20),
            Nome     NVARCHAR(255),
            Tipo     NVARCHAR(20),
            Situacao NVARCHAR(20),
            Acao     NVARCHAR(50),
            Detalhe  NVARCHAR(MAX)
        )
    """)
    conn.commit()


def salvar_log_gedoc(data_hora, cpf, nome, tipo, situacao, acao, detalhe=""):
    global _db_conn
    for tentativa in range(2):
        try:
            conn = _get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO LogIntegracaoGEDOC "
                "(DataHora, CPF, Nome, Tipo, Situacao, Acao, Detalhe) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                data_hora, cpf, nome, tipo, situacao, acao, detalhe or "",
            )
            conn.commit()
            return
        except pyodbc.OperationalError:
            _db_conn = None
            if tentativa == 1:
                raise
