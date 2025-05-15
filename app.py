# Bibliotecas ----
from shiny import App, ui, render
from faicons import icon_svg
from shinyswatch import theme
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.colors # Para converter cores para RGBA para o intervalo de confiança
import sys # Para df.info(buf=sys.stdout)
import traceback # Para imprimir tracebacks completos

# Dados ----
try:
    print("--- Carregando arquivos Parquet ---")
    cambio = pd.read_parquet("previsao/cambio.parquet")
    print("cambio.parquet carregado.")
    ipca = pd.read_parquet("previsao/ipca.parquet")
    print("ipca.parquet carregado.")
    pib = pd.read_parquet("previsao/pib.parquet")
    print("pib.parquet carregado.")
    selic = pd.read_parquet("previsao/selic.parquet")
    print("selic.parquet carregado.")
    print("--- Arquivos Parquet carregados com sucesso ---")
except FileNotFoundError as e:
    print(f"ERRO CRÍTICO: Arquivo de dados não encontrado. Verifique os caminhos: {e}")
    print("AVISO: Inicializando DataFrames de dados como vazios. O dashboard pode não funcionar como esperado.")
    cols = ['Valor', 'Tipo', 'Intervalo Inferior', 'Intervalo Superior']
    empty_idx = pd.to_datetime([])
    cambio = pd.DataFrame(columns=cols, index=empty_idx)
    ipca = pd.DataFrame(columns=cols, index=empty_idx)
    pib = pd.DataFrame(columns=cols, index=empty_idx)
    selic = pd.DataFrame(columns=cols, index=empty_idx)
except Exception as e_parquet:
    print(f"ERRO CRÍTICO ao carregar arquivos Parquet: {e_parquet}"); traceback.print_exc()
    print("AVISO: Inicializando DataFrames de dados como vazios. O dashboard pode não funcionar como esperado.")
    cols = ['Valor', 'Tipo', 'Intervalo Inferior', 'Intervalo Superior']
    empty_idx = pd.to_datetime([])
    cambio = pd.DataFrame(columns=cols, index=empty_idx)
    ipca = pd.DataFrame(columns=cols, index=empty_idx)
    pib = pd.DataFrame(columns=cols, index=empty_idx)
    selic = pd.DataFrame(columns=cols, index=empty_idx)


dfs_to_check = {"cambio": cambio, "ipca": ipca, "pib": pib, "selic": selic}
for name, df_check in dfs_to_check.items():
    if not isinstance(df_check.index, pd.DatetimeIndex):
        print(f"AVISO CRÍTICO: O índice do DataFrame '{name}' não é um DatetimeIndex. Tentando converter...")
        try:
            if not df_check.index.empty: df_check.index = pd.to_datetime(df_check.index)
            else: df_check.index = pd.to_datetime([])
        except Exception as e_idx:
            print(f"Falha ao converter índice de '{name}': {e_idx}. Recriando com índice DatetimeIndex vazio.")
            dfs_to_check[name] = pd.DataFrame(columns=df_check.columns, index=pd.to_datetime([]))
cambio, ipca, pib, selic = dfs_to_check["cambio"], dfs_to_check["ipca"], dfs_to_check["pib"], dfs_to_check["selic"]

datas = {
    "min": pib.index.min().date() if not pib.empty and pib.index.min() is not pd.NaT else pd.Timestamp('2019-01-01').date(),
    "max": selic.index.max().date() if not selic.empty and selic.index.max() is not pd.NaT else pd.Timestamp.now().date(),
    "value": pib.index[-36].date() if not pib.empty and len(pib.index) >= 36 and pib.index[-36] is not pd.NaT else \
             (pib.index.min().date() if not pib.empty and pib.index.min() is not pd.NaT else pd.Timestamp('2020-01-01').date())
}

all_dfs_list = [df for name, df in dfs_to_check.items() if isinstance(df, pd.DataFrame) and not df.empty and 'Tipo' in df.columns]
if all_dfs_list:
    try:
        modelos_df = pd.concat(all_dfs_list); modelos_disponiveis = modelos_df[~modelos_df['Tipo'].isin(['Câmbio', 'IPCA', 'PIB', 'Selic'])]['Tipo'].unique().tolist()
    except Exception as e_concat: print(f"Erro ao criar 'modelos_disponiveis': {e_concat}"); modelos_disponiveis = []
else: modelos_disponiveis = []; print("AVISO: 'modelos_disponiveis' estará vazio.")
print(f"Modelos disponíveis para seleção: {modelos_disponiveis}")

# Interface do Usuário ----
app_ui = ui.page_navbar(
    # Primeiro, os argumentos posicionais (os painéis de navegação principais)
    ui.nav_panel(
        "",
        ui.layout_columns(
            ui.navset_card_underline(ui.nav_panel("", ui.output_ui("ipca_plt_ui"), icon=icon_svg("chart-line"), value="plt"), ui.nav_panel("", ui.output_data_frame("ipca_tbl"), icon=icon_svg("table"), value="tbl"), title= ui.div(ui.strong("Inflação (IPCA)")), selected="plt"),
            ui.navset_card_underline(ui.nav_panel("", ui.output_ui("cambio_plt_ui"), icon=icon_svg("chart-line"), value="plt"), ui.nav_panel("", ui.output_data_frame("cambio_tbl"), icon=icon_svg("table"), value="tbl"), title= ui.div(ui.strong("Taxa de Câmbio (BRL/USD)")), selected="plt")
        ),
        
        ui.layout_columns(
            ui.navset_card_underline(ui.nav_panel("", ui.output_ui("pib_plt_ui"), icon=icon_svg("chart-line"), value="plt"), ui.nav_panel("", ui.output_data_frame("pib_tbl"), icon=icon_svg("table"), value="tbl"), title=ui.div(ui.strong("Atividade Econômica (PIB)")), selected="plt"),
            ui.navset_card_underline(ui.nav_panel("", ui.output_ui("selic_plt_ui"), icon=icon_svg("chart-line"), value="plt"), ui.nav_panel("", ui.output_data_frame("selic_tbl"), icon=icon_svg("table"), value="tbl"), title= ui.div(ui.strong("Taxa de Juros (SELIC)")), selected="plt")
        )
    ),
 
    # Agora, os argumentos de palavra-chave
    header=ui.head_content(
        ui.tags.script(src="https://cdn.plot.ly/plotly-latest.min.js")
    ),
title=ui.div(
        # Imagem da Logomarca
        ui.img(
            src="https://i.imgur.com/dGvmnLA.png",
            style=(
                "height: 70px; "  # Tente um valor fixo, ajuste conforme necessário
                "width: auto; "     # Mantém a proporção
                "margin-right: 10px; "
                "flex-shrink: 0;"   # Impede que a imagem encolha se não houver espaço
            )
        ),
        # Texto ao lado da logomarca
        ui.span(
            "Painel de Previsões Macroeconômicas",
            style=(
                "color: #f0f0f0; "
                "font-size: 1.5rem; " # Ajuste o tamanho da fonte se necessário
                "font-weight: bold; "
                "white-space: nowrap; " # Impede que o texto quebre em várias linhas
                "line-height: 40px;"    # Tenta alinhar com a altura da imagem
            )
        ),
        # Estilo CSS para o ui.div que o torna um container flexbox
        style=(
            "display: flex; "         # Habilita o layout flexbox (itens lado a lado por padrão)
            "flex-direction: row; "   # Garante que os itens fiquem em linha (horizontalmente)
            "align-items: center; "   # Alinha os itens verticalmente ao centro
            "height: 100%;"            # Faz o div tentar usar a altura total da área do título
            "overflow: hidden;"       # Pode ajudar se o conteúdo estiver tentando estourar
        )
    ),

    window_title="<b>Painel de Previsões Macroeconômicas</b>", # Ajustado para corresponder ao texto do título
   
     
    fillable=True, 
    fillable_mobile=True, 
    theme=theme.flatly,
    sidebar=ui.sidebar(
        ui.markdown("<b> Dashboard para acompanhar e simular previsões de indicadores macroeconômicos do Brasil.</b>"),
        ui.input_checkbox_group(id="modelo", label=ui.strong("Selecionar modelos:"), choices=modelos_disponiveis, selected=modelos_disponiveis),
        ui.input_date(id="inicio", label=ui.strong("Início do gráfico:"), value=datas["value"], min=datas["min"], max=datas["max"], format="mm/yyyy", startview="year", language="pt-BR", width="100%"),
        ui.input_checkbox(id="ic", label=ui.strong("Intervalo de confiança"), value=True, width="100%"),
        ui.markdown("<b> Elaboração</b>: Raimundo Casé - economista")
    )
)

# Servidor ----
def server(input, output, session):
    color_map = {
        "IPCA": "DarkBlue", "Câmbio": "#8B4513", "PIB": "black", "Selic": "OrangeRed",
        "IA": "green", "Ridge Regression": "blue", "Bayesian Ridge Regression": "orange",
        "Huber Regression": "red", "Ensemble": "brown"
    }

    def plotar_grafico_plotly(y_tipo_principal, df_completo, y_label_grafico):
        print(f"\n--- Entrando em plotar_grafico_plotly para: {y_tipo_principal} ---")
        if not isinstance(df_completo, pd.DataFrame) or df_completo.empty or not isinstance(df_completo.index, pd.DatetimeIndex) or df_completo.index.empty:
            print(f"ERRO INICIAL plotar_grafico_plotly({y_tipo_principal}): df_completo vazio/inválido."); fig_erro = go.Figure(); fig_erro.update_layout(title_text=f"Dados de '{y_tipo_principal}' não disponíveis/inválidos.", height=400, xaxis_visible=False, yaxis_visible=False); return fig_erro
        print(f"df_completo para '{y_tipo_principal}' Shape: {df_completo.shape}. Head:\n{df_completo.head()}"); print("Info:"); df_completo.info(buf=sys.stdout)
        modelos_selecionados_input = list(input.modelo()) if input.modelo() is not None else []
        print(f"Modelos selecionados para '{y_tipo_principal}': {modelos_selecionados_input}")
        if 'Tipo' not in df_completo.columns: print(f"ERRO plotar_grafico_plotly({y_tipo_principal}): Coluna 'Tipo' ausente."); fig_erro_tipo = go.Figure(); fig_erro_tipo.update_layout(title_text=f"Coluna 'Tipo' ausente nos dados de '{y_tipo_principal}'.", height=400, xaxis_visible=False, yaxis_visible=False); return fig_erro_tipo
        modelos_a_plotar = [y_tipo_principal] + [m for m in modelos_selecionados_input if m in df_completo['Tipo'].unique()]
        print(f"Modelos a plotar para '{y_tipo_principal}': {modelos_a_plotar}")
        try:
            data_inicio_input_val = input.inicio(); data_inicio_input = pd.to_datetime(data_inicio_input_val, errors='coerce') if isinstance(data_inicio_input_val, str) else pd.to_datetime(data_inicio_input_val)
            if pd.NaT == data_inicio_input: raise ValueError("Data convertida para NaT")
            print(f"Data início para '{y_tipo_principal}': {data_inicio_input}")
        except Exception as e_date: fallback_date = pd.Timestamp('2000-01-01'); print(f"AVISO plotar_grafico_plotly({y_tipo_principal}): Data início inválida ('{input.inicio()}'), usando fallback {fallback_date}. Erro: {e_date}"); data_inicio_input = fallback_date
        df_plot = df_completo.copy().reset_index().rename(columns={'index': 'Data'}); df_plot['Data'] = pd.to_datetime(df_plot['Data'], errors='coerce'); df_plot = df_plot.dropna(subset=['Data'])
        df_filtrado = df_plot[df_plot['Tipo'].isin(modelos_a_plotar) & (df_plot['Data'] >= data_inicio_input)]
        print(f"df_filtrado para '{y_tipo_principal}'. Shape: {df_filtrado.shape}. Head:\n{df_filtrado.head()}")
        if df_filtrado.empty: print(f"AVISO: df_filtrado para '{y_tipo_principal}' VAZIO. Retornando 'sem dados'."); fig_vazio = go.Figure(); fig_vazio.update_layout(annotations=[dict(text="Sem dados para exibir com filtros.", xref="paper", yref="paper", showarrow=False, font_size=16)], height=400, xaxis_visible=False, yaxis_visible=False); return fig_vazio
        categorias_ordenadas = [y_tipo_principal] + sorted(list(set(df_filtrado['Tipo'].unique()) - {y_tipo_principal}))
        df_filtrado['Tipo'] = pd.Categorical(df_filtrado['Tipo'], categories=categorias_ordenadas, ordered=True); df_filtrado = df_filtrado.sort_values(by=['Tipo', 'Data'])
        fig = px.line(df_filtrado, x="Data", y="Valor", color="Tipo", labels={"Data": "", "Valor": y_label_grafico, "Tipo": ""}, color_discrete_map=color_map)
        if input.ic() and 'Intervalo Inferior' in df_filtrado.columns and 'Intervalo Superior' in df_filtrado.columns:
            for modelo_tipo_ic in categorias_ordenadas:
                if modelo_tipo_ic == y_tipo_principal: continue
                df_modelo_ic = df_filtrado[(df_filtrado['Tipo'] == modelo_tipo_ic) & df_filtrado['Intervalo Inferior'].notna() & df_filtrado['Intervalo Superior'].notna()]
                if not df_modelo_ic.empty:
                    cor_original_modelo = color_map.get(modelo_tipo_ic, "grey")
                    try: rgba_color = matplotlib.colors.to_rgba(cor_original_modelo, alpha=0.2); cor_fill = f'rgba({int(rgba_color[0]*255)},{int(rgba_color[1]*255)},{int(rgba_color[2]*255)},{rgba_color[3]})'
                    except ValueError: cor_fill = 'rgba(128,128,128,0.2)'
                    fig.add_trace(go.Scatter(x=df_modelo_ic['Data'].tolist() + df_modelo_ic['Data'].tolist()[::-1], y=df_modelo_ic['Intervalo Superior'].tolist() + df_modelo_ic['Intervalo Inferior'].tolist()[::-1], fill='toself', fillcolor=cor_fill, line=dict(color='rgba(255,255,255,0)'), hoverinfo="skip", showlegend=False, name=f"IC {modelo_tipo_ic}"))
        fig.update_layout(legend_title_text=" ", legend_orientation="h", legend_xanchor="center", legend_x=0.5, legend_yanchor="bottom", legend_y=-0.2, hovermode="x", height=500, margin=dict(t=40, b=120, l=60, r=40), plot_bgcolor="#f0f3ff", paper_bgcolor="#f3f3f4", font = dict(family="Times New Roman, Arial", size=14), hoverlabel_align="left", hoverlabel_namelength=-1, xaxis_hoverformat="")
    
    # Dentro da função plotar_grafico_plotly, após fig.update_layout(...)
        fig.update_xaxes(
            title_text="",
            dtick="M12",      # Isso define os marcadores principais do eixo (a cada 12 meses)
            tickformat="%Y",  # Isso formata esses marcadores principais para mostrar apenas o ano
            ##hoverformat="%m/%Y" # NOVO: Isso formata o valor de X exibido no tooltip para Mês/Ano
                                 # Exemplo: 01/2023, 02/2023, etc.
                                 # Se seus dados tiverem dias específicos que são importantes,
                                 # você pode usar "%d/%m/%Y"
            showgrid=True, gridwidth=1, gridcolor ="rgba(128,128,128,0.2)", tickfont_color="black"
        )

 # NOVO: Definir o hovertemplate para todos os traços, AGORA INCLUINDO A DATA
        fig.update_traces(
             hovertemplate="<b>%{data.name}</b><br>" + # Nome da série (ex: IPCA, Ridge Regression) em negrito
                  "Data: %{x|%m/%Y}<br>" +       # Data formatada como Mês/Ano
                  f"{y_label_grafico}: %{{y:.2f}}" +  # Rótulo do eixo Y e valor com 2 casas decimais
                  "<extra></extra>" # Remove o "trace N" e outras informações extras
        )

        print(f"Figura final para '{y_tipo_principal}' criada e customizada. Traços: {len(fig.data) if fig and hasattr(fig, 'data') else 'Fig None/sem data'}"); print(f"--- Saindo de plotar_grafico_plotly para: {y_tipo_principal} ---\n")
        return fig

    def imprimir_tabela(df_completo, y_tipo_principal):
        print(f"\n--- Entrando em imprimir_tabela para: {y_tipo_principal} ---")
        if not isinstance(df_completo, pd.DataFrame) or df_completo.empty or not isinstance(df_completo.index, pd.DatetimeIndex) or df_completo.index.empty:
            print(f"AVISO imprimir_tabela({y_tipo_principal}): df_completo vazio/inválido."); return render.DataGrid(pd.DataFrame({"Mensagem": [f"Dados da tabela para {y_tipo_principal} não disponíveis"]}), height="400px", width="100%")
        df_tabela = df_completo.reset_index().rename(columns={"index": "Data", "Valor": "Previsão", "Tipo": "Modelo"}); df_tabela['Data'] = pd.to_datetime(df_tabela['Data'], errors='coerce'); df_tabela = df_tabela.dropna(subset=['Data'])
        if 'Modelo' not in df_tabela.columns: print(f"AVISO imprimir_tabela({y_tipo_principal}): Coluna 'Modelo' ausente."); return render.DataGrid(pd.DataFrame({"Mensagem": [f"Erro ao processar tabela para {y_tipo_principal}"]}), height="400px", width="100%")
        df_tabela = df_tabela[df_tabela['Modelo'] != y_tipo_principal]; df_tabela['Data'] = df_tabela['Data'].dt.strftime("%m/%Y")
        cols_para_mostrar = ["Data", "Modelo", "Previsão"]
        if 'Intervalo Inferior' in df_tabela.columns: df_tabela = df_tabela.rename(columns={"Intervalo Inferior": "IC Inferior"}); cols_para_mostrar.append("IC Inferior")
        if 'Intervalo Superior' in df_tabela.columns: df_tabela = df_tabela.rename(columns={"Intervalo Superior": "IC Superior"}); cols_para_mostrar.append("IC Superior")
        for col_num in ["Previsão", "IC Inferior", "IC Superior"]:
            if col_num in df_tabela.columns: df_tabela[col_num] = pd.to_numeric(df_tabela[col_num], errors='coerce').round(2)
        df_final_tabela = df_tabela[[col for col in cols_para_mostrar if col in df_tabela.columns]]
        print(f"Tabela para '{y_tipo_principal}' processada. Shape: {df_final_tabela.shape}"); return render.DataGrid(df_final_tabela, summary=False, selection_mode="none", height="400px", width="100%")

    def render_plotly_fig(fig_name, y_tipo_principal, df_completo, y_label_grafico):
        print(f"\n--- Renderizando UI para: {fig_name} ---")
        try:
            fig = plotar_grafico_plotly(y_tipo_principal=y_tipo_principal, df_completo=df_completo, y_label_grafico=y_label_grafico)
            if fig is not None and hasattr(fig, 'data'): # Verifica se fig é uma figura Plotly válida
                print(f"Figura {y_tipo_principal} recebida. Traços: {len(fig.data)}. Tentando to_html...")
                # Alterado para include_plotlyjs=False pois carregamos globalmente
                html_output = fig.to_html(full_html=False, include_plotlyjs=False) 
                print(f"Renderizando HTML para {y_tipo_principal} (tamanho: {len(html_output)}).")
                return ui.HTML(html_output)
            elif fig is not None: # É um objeto Figure, mas pode não ter 'data' (ex: figura de erro)
                print(f"AVISO em {fig_name}: Figura {y_tipo_principal} recebida, mas pode não ter 'data'. Tentando to_html.")
                html_output = fig.to_html(full_html=False, include_plotlyjs=False)
                return ui.HTML(html_output)
            else: # fig é None
                print(f"ERRO em {fig_name}: plotar_grafico_plotly retornou None para {y_tipo_principal}.")
                return ui.HTML(f"<div style='height:400px; display:flex; align-items:center; justify-content:center; border:1px solid #ccc;'><p>Erro: Gráfico de {y_tipo_principal} não pôde ser criado.</p></div>")
        except Exception as e:
            print(f"EXCEÇÃO GRAVE em {fig_name}: {e}"); traceback.print_exc()
            return ui.HTML(f"<div style='height:400px; display:flex; align-items:center; justify-content:center; border:1px solid #ccc;'><p>Exceção ao gerar gráfico de {y_tipo_principal}: {e}</p></div>")

    @render.ui
    def ipca_plt_ui(): return render_plotly_fig("ipca_plt_ui", "IPCA", ipca, "Var. %")
    @render.ui
    def cambio_plt_ui(): return render_plotly_fig("cambio_plt_ui", "Câmbio", cambio, "R$/US$")
    @render.ui
    def pib_plt_ui(): return render_plotly_fig("pib_plt_ui", "PIB", pib, "Var. % anual")
    @render.ui
    def selic_plt_ui(): return render_plotly_fig("selic_plt_ui", "Selic", selic, "% a.a.")

    @render.data_frame
    def ipca_tbl(): return imprimir_tabela(ipca, "IPCA")
    @render.data_frame
    def cambio_tbl(): return imprimir_tabela(cambio, "Câmbio")
    @render.data_frame
    def pib_tbl(): return imprimir_tabela(pib, "PIB")
    @render.data_frame
    def selic_tbl(): return imprimir_tabela(selic, "Selic")

# Shiny dashboard ----
print("--- Definindo App Shiny ---")
app = App(app_ui, server)
print("--- App Shiny Definido. Execute com 'shiny run app.py' ---")