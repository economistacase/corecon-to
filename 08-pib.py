# Bibliotecas
from skforecast.ForecasterAutoreg import ForecasterAutoreg
from sklearn.linear_model import Ridge, BayesianRidge
from sklearn.preprocessing import PowerTransformer
from io import StringIO
import google.generativeai as genai
import pandas as pd
import numpy as np
import os

# Definições e configurações globais
h = 4 # horizonte de previsão
inicio_treino = pd.to_datetime("1997-10-01") # amostra inicial de treinamento
semente = 1984 # semente para reprodução

# Função para transformar dados, conforme definido nos metadados
def transformar(x, tipo):

  switch = {
      "1": lambda x: x,
      "2": lambda x: x.diff(),
      "3": lambda x: x.diff().diff(),
      "4": lambda x: np.log(x),
      "5": lambda x: np.log(x).diff(),
      "6": lambda x: np.log(x).diff().diff()
  }

  if tipo not in switch:
      raise ValueError("Tipo inválido")

  return switch[tipo](x)

# Planilha de metadados
metadados = (
    pd.read_excel(
        io = "https://docs.google.com/spreadsheets/d/1x8Ugm7jVO7XeNoxiaFPTPm1mfVc3JUNvvVqVjCioYmE/export?format=xlsx",
        sheet_name = "Metadados",
        dtype = str,
        index_col = "Identificador"
        )
    .filter(["Transformação"])
)

# Importa dados online
dados_brutos_m = pd.read_parquet("dados/df_mensal.parquet")
dados_brutos_t = pd.read_parquet("dados/df_trimestral.parquet")

# Converte frequência
dados_tratados = (
    dados_brutos_m
    .resample("QS")
    .mean()
    .join(
        other = (
            dados_brutos_t
            .set_index(pd.PeriodIndex(dados_brutos_t.index, freq = "Q").to_timestamp())
            .resample("QS")
            .mean()
            ),
        how = "outer"
    )
    .rename_axis("data", axis = "index")
)

# Separa Y
y = dados_tratados.pib.dropna()

# Separa X
x = dados_tratados.drop(labels = ["pib"], axis = "columns").copy()

# Computa transformações
for col in x.drop(labels = ["saldo_caged_antigo", "saldo_caged_novo"], axis = "columns").columns.to_list():
  x[col] = transformar(x[col], metadados.loc[col, "Transformação"])

# Filtra amostra
y = y[y.index >= inicio_treino]
x_alem_de_y = x.query("index >= @y.index.max()")
x = x.query("index >= @inicio_treino and index <= @y.index.max()")

# Conta por coluna proporção de NAs em relação ao nº de obs. de Y
prop_na = x.isnull().sum() / y.shape[0]

# Remove variáveis que possuem mais de 20% de NAs
x = x.drop(labels = prop_na[prop_na >= 0.2].index.to_list(), axis = "columns")

# Preenche NAs restantes com a vizinhança
x = x.bfill().ffill()

# Seleção final de variáveis
x_reg = [
    "uci_ind_fgv",
    "expec_pib",
    "prod_ind_metalurgia"
    ]
# + 2 lags


# Reestima os 2 melhores modelos com amostra completa
modelo1 = ForecasterAutoreg(
    regressor = Ridge(),
    lags = 2,
    transformer_y = PowerTransformer(),
    transformer_exog = PowerTransformer()
    )
modelo1.fit(y, x[x_reg])

modelo2 = ForecasterAutoreg(
    regressor = BayesianRidge(),
    lags = 2,
    transformer_y = PowerTransformer(),
    transformer_exog = PowerTransformer()
    )
modelo2.fit(y, x[x_reg])


# Período de previsão fora da amostra
periodo_previsao = pd.date_range(
    start = modelo1.last_window.index[1] + pd.offsets.QuarterBegin(1),
    end = modelo1.last_window.index[1] + pd.offsets.QuarterBegin(h + 1),
    freq = "QS"
    )


# Constrói cenário para Utilização da Capacidade Instalada (uci_ind_fgv)
dados_cenario_uci_ind_fgv = (
    x
    .filter(["uci_ind_fgv"])
    .dropna()
    .query("index >= @inicio_treino")
    .assign(trim = lambda x: x.index.quarter)
    .groupby(["trim"], as_index = False)
    .uci_ind_fgv
    .median()
    .set_index("trim")
    .join(
        other = (
            periodo_previsao
            .rename("data")
            .to_frame()
            .assign(trim = lambda x: x.data.dt.quarter)
            .drop("data", axis = "columns")
            .reset_index()
            .set_index("trim")
        ),
        how = "outer"
    )
    .sort_values(by = "data")
    .set_index("data")
)

# Coleta dados de expectativas do PIB (expec_pib)
dados_focus_expec_pib = pd.read_csv(
    filepath_or_buffer = f"https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoTrimestrais?$filter=Indicador%20eq%20'PIB%20Total'%20and%20baseCalculo%20eq%200%20and%20Data%20ge%20'{periodo_previsao.min().strftime('%Y-%m-%d')}'&$format=text/csv",
    decimal = ",",
    converters = {"Data": pd.to_datetime}
    )

# Data do relatório Focus usada para construir cenário para Expectativas PIB (expec_pib)
data_focus_expec_pib = (
    dados_focus_expec_pib
    .assign(
        DataReferencia = lambda x: pd.PeriodIndex(
            x.DataReferencia.str.replace(r"(\d{1})/(\d{4})", r"\2-Q\1", regex = True),
            freq = "Q"
            ).to_timestamp()
    )
    .query("DataReferencia in @periodo_previsao or DataReferencia == @modelo1.last_window.index[1]")
    .Data
    .value_counts()
    .to_frame()
    .reset_index()
    .query("count >= @h")
    .query("Data == Data.max()")
    .head(1)
    .Data
    .to_list()[0]
)

# Constrói cenário para expectativas do PIB (expec_pib)
dados_cenario_expec_pib = (
    dados_focus_expec_pib
    .assign(
        DataReferencia = lambda x: pd.PeriodIndex(
            x.DataReferencia.str.replace(r"(\d{1})/(\d{4})", r"\2-Q\1", regex = True),
            freq = "Q"
            ).to_timestamp()
    )
    .query("DataReferencia in @periodo_previsao or DataReferencia == @modelo1.last_window.index[1]")
    .query("Data == @data_focus_expec_pib")
    .query("DataReferencia in @periodo_previsao")
    .sort_values(by = "DataReferencia")
    .set_index("DataReferencia")
    .filter(["Mediana"])
    .rename(columns = {"Mediana": "expec_pib"})
    .dropna()
)

# Constrói cenário para Produção Industrial (prod_ind_metalurgia)
dados_cenario_prod_ind_metalurgia = (
    x
    .filter(["prod_ind_metalurgia"])
    .dropna()
    .query("index >= @inicio_treino")
    .assign(trim = lambda x: x.index.quarter)
    .groupby(["trim"], as_index = False)
    .prod_ind_metalurgia
    .median()
    .set_index("trim")
    .join(
        other = (
            periodo_previsao
            .rename("data")
            .to_frame()
            .assign(trim = lambda x: x.data.dt.quarter)
            .drop("data", axis = "columns")
            .reset_index()
            .set_index("trim")
        ),
        how = "outer"
    )
    .sort_values(by = "data")
    .set_index("data")
)

# Junta cenários e gera dummies sazonais
dados_cenarios = (
    dados_cenario_uci_ind_fgv
    .join(
        other = [
            dados_cenario_expec_pib,
            dados_cenario_prod_ind_metalurgia
            ],
        how = "outer"
        )
    .asfreq("QS")
)

# Produz previsões
previsao1 = (
   modelo1.predict_interval(
      steps = h,
      exog = dados_cenarios,
      n_boot = 5000,
      random_state = semente
      )
    .assign(Tipo = "Ridge")
    .rename(
       columns = {
          "pred": "Valor", 
          "lower_bound": "Intervalo Inferior", 
          "upper_bound": "Intervalo Superior"
          }
    )
)

previsao2 = (
   modelo2.predict_interval(
      steps = h,
      exog = dados_cenarios,
      n_boot = 5000,
      random_state = semente
      )
    .assign(Tipo = "Bayesian Ridge")
    .rename(
       columns = {
          "pred": "Valor", 
          "lower_bound": "Intervalo Inferior", 
          "upper_bound": "Intervalo Superior"
          }
    )
)

y.to_frame().join(x[x_reg]).to_csv("dados/pib.csv")
prompt = f"""
Assume that you are in {pd.to_datetime("today").strftime("%B %d, %Y")}. 
Please give me your best forecast of Gross Domestic Product (GDP) for Brazil, 
measured in annual percentage variation (accumulated rate in four quarters in 
relation to the same period of the previous year) and published by IBGE, for 
{periodo_previsao.min().to_period(freq = "Q").strftime("%Y Q%q")} to {periodo_previsao.max().to_period(freq = "Q").strftime("%Y Q%q")}. 
Use the historical GDP data from the attached CSV file named "pib.csv", where "pib" 
is the target column, "data" is the date column and the others are exogenous variables. 
Please give me numeric values for these forecasts, in a CSV like format with 
a header, and nothing more. Do not use any information that was not available 
to you as of {pd.to_datetime("today").strftime("%B %d, %Y")} to formulate these 
forecasts.
"""

genai.configure(api_key = os.environ["GEMINI_API_KEY"])
modelo_ia = genai.GenerativeModel(model_name = "gemini-1.5-pro")
arquivo = genai.upload_file("dados/pib.csv")
previsao3 = pd.read_csv(
    filepath_or_buffer = StringIO(modelo_ia.generate_content([prompt, arquivo]).text),
    names = ["date", "Valor"],
    skiprows = 1,
    index_col = "date",
    converters = {"date": pd.to_datetime}
    ).assign(Tipo = "IA")

# Salvar previsões
pasta = "previsao"
if not os.path.exists(pasta):
  os.makedirs(pasta)
  
pd.concat(
    [y.rename("Valor").to_frame().assign(Tipo = "PIB"),
    previsao1,
    previsao2,
    previsao3
    ]).to_parquet("previsao/pib.parquet")
