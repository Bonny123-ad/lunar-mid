import os
import json
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# ============================================================
# CONFIGURAÇÃO
# ============================================================

load_dotenv()

TOKEN = os.getenv("TOKEN")

PREFIX = "!"

# IDs opcionais — coloque 0 se não quiser usar
CATEGORIA_TICKETS_ID = 0
CANAL_LOGS_ID = 0

ARQUIVO_DADOS = "dados.json"

# Valores fictícios disponíveis
VALORES = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

MODOS = {
    "normal": "🎮 AP NORMAL",
    "full": "🔫 AP FULL UMP + XM8"
}


# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents
)


# ============================================================
# BANCO DE DADOS SIMPLES
# ============================================================

def carregar_dados():
    if not os.path.exists(ARQUIVO_DADOS):
        return {
            "usuarios": {},
            "partidas": []
        }

    try:
        with open(ARQUIVO_DADOS, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except:
        return {
            "usuarios": {},
            "partidas": []
        }


def salvar_dados(dados):
    with open(
        ARQUIVO_DADOS,
        "w",
        encoding="utf-8"
    ) as arquivo:
        json.dump(
            dados,
            arquivo,
            indent=4,
            ensure_ascii=False
        )


dados = carregar_dados()


def criar_usuario(user_id):

    user_id = str(user_id)

    if user_id not in dados["usuarios"]:
        dados["usuarios"][user_id] = {
            "saldo": 100,
            "vitorias": 0,
            "derrotas": 0,
            "partidas": 0
        }

        salvar_dados(dados)


def obter_usuario(user_id):
    criar_usuario(user_id)
    return dados["usuarios"][str(user_id)]


# ============================================================
# EMBEDS
# ============================================================

def embed_painel():

    embed = discord.Embed(
        title="🎯 SALINHAS FREE FIRE",
        description=(
            "Escolha o tipo de partida abaixo.\n\n"

            "🎮 **AP NORMAL**\n"
            "Partida normal.\n\n"

            "🔫 **AP FULL UMP + XM8**\n"
            "Partida com UMP + XM8.\n\n"

            "💰 Os valores apresentados são "
            "**créditos fictícios**."
        ),
        color=discord.Color.blue()
    )

    embed.set_footer(
        text="Sistema de simulação • Sem dinheiro real"
    )

    return embed


# ============================================================
# BOTÃO DO PAINEL
# ============================================================

class PainelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="AP NORMAL",
        emoji="🎮",
        style=discord.ButtonStyle.primary,
        custom_id="sim_ap_normal"
    )
    async def ap_normal(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            "🎮 **AP NORMAL**\n\n"
            "Escolha o valor fictício:",
            view=ValorView("normal"),
            ephemeral=True
        )

    @discord.ui.button(
        label="AP FULL UMP + XM8",
        emoji="🔫",
        style=discord.ButtonStyle.danger,
        custom_id="sim_ap_full"
    )
    async def ap_full(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            "🔫 **AP FULL UMP + XM8**\n\n"
            "Escolha o valor fictício:",
            view=ValorView("full"),
            ephemeral=True
        )


# ============================================================
# SELEÇÃO DE VALOR
# ============================================================

class ValorSelect(discord.ui.Select):

    def __init__(self, modo):

        self.modo = modo

        options = []

        for valor in VALORES:

            options.append(
                discord.SelectOption(
                    label=f"{valor} créditos",
                    description=f"Entrada fictícia de {valor}",
                    value=str(valor)
                )
            )

        super().__init__(
            placeholder="Escolha o valor...",
            options=options,
            custom_id=f"valor_{modo}"
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        valor = int(self.values[0])

        await criar_ticket(
            interaction,
            self.modo,
            valor
        )


class ValorView(discord.ui.View):

    def __init__(self, modo):

        super().__init__(timeout=120)

        self.add_item(
            ValorSelect(modo)
        )


# ============================================================
# CRIAR TICKET
# ============================================================

async def criar_ticket(
    interaction,
    modo,
    valor
):

    guild = interaction.guild
    usuario = interaction.user

    # Procura categoria configurada
    categoria = None

    if CATEGORIA_TICKETS_ID != 0:
        categoria = guild.get_channel(
            CATEGORIA_TICKETS_ID
        )

    # Verifica se já existe ticket
    for canal in guild.text_channels:

        if canal.name == f"ticket-{usuario.id}":

            await interaction.response.send_message(
                f"❌ Você já possui um ticket: {canal.mention}",
                ephemeral=True
            )

            return

    # Permissões
    overwrites = {

        guild.default_role:
            discord.PermissionOverwrite(
                view_channel=False
            ),

        usuario:
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
    }

    # Cargos que podem mediar
    for role in guild.roles:

        nome = role.name.lower()

        if (
            "mediador" in nome
            or "staff" in nome
            or "admin" in nome
        ):

            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

    # Criação do canal
    canal = await guild.create_text_channel(

        name=f"ticket-{usuario.id}",

        category=categoria,

        overwrites=overwrites
    )

    # Embed
    embed = discord.Embed(
        title="🎫 TICKET DE SALINHA",
        color=discord.Color.green()
    )

    embed.add_field(
        name="👤 Jogador",
        value=usuario.mention,
        inline=False
    )

    embed.add_field(
        name="🎮 Modo",
        value=MODOS[modo],
        inline=False
    )

    embed.add_field(
        name="💰 Valor fictício",
        value=f"**{valor} créditos**",
        inline=False
    )

    embed.add_field(
        name="📊 Status",
        value="🟡 Aguardando mediador",
        inline=False
    )

    embed.set_footer(
        text="SIMULAÇÃO • Sem dinheiro real"
    )

    await canal.send(
        content=usuario.mention,
        embed=embed,
        view=TicketView(
            usuario.id,
            modo,
            valor
        )
    )

    await interaction.response.send_message(
        f"✅ Ticket criado: {canal.mention}",
        ephemeral=True
    )


# ============================================================
# TICKET
# ============================================================

class TicketView(discord.ui.View):

    def __init__(
        self,
        dono_id,
        modo,
        valor
    ):

        super().__init__(timeout=None)

        self.dono_id = dono_id
        self.modo = modo
        self.valor = valor


    @discord.ui.button(
        label="Assumir",
        emoji="👤",
        style=discord.ButtonStyle.success,
        custom_id="ticket_assumir"
    )
    async def assumir(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        membro = interaction.user

        pode_assumir = (
            membro.guild_permissions.administrator
            or any(
                "mediador" in role.name.lower()
                or "staff" in role.name.lower()
                or "admin" in role.name.lower()
                for role in membro.roles
            )
        )

        if not pode_assumir:

            await interaction.response.send_message(
                "❌ Você não pode assumir tickets.",
                ephemeral=True
            )

            return

        embed = discord.Embed(
            title="👤 TICKET ASSUMIDO",
            description=(
                f"**Mediador:** {membro.mention}\n"
                f"**Modo:** {MODOS[self.modo]}\n"
                f"**Valor:** {self.valor} créditos"
            ),
            color=discord.Color.green()
        )

        await interaction.channel.send(
            embed=embed
        )

        await interaction.response.send_message(
            "✅ Você assumiu este ticket.",
            ephemeral=True
        )


    @discord.ui.button(
        label="Dados da Sala",
        emoji="🔑",
        style=discord.ButtonStyle.primary,
        custom_id="ticket_sala"
    )
    async def dados_sala(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        # Apenas staff/mediador
        membro = interaction.user

        pode = (
            membro.guild_permissions.administrator
            or any(
                "mediador" in role.name.lower()
                or "staff" in role.name.lower()
                or "admin" in role.name.lower()
                for role in membro.roles
            )
        )

        if not pode:

            await interaction.response.send_message(
                "❌ Apenas mediadores podem enviar os dados.",
                ephemeral=True
            )

            return

        await interaction.response.send_modal(
            SalaModal()
        )


    @discord.ui.button(
        label="Resultado",
        emoji="🏆",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_resultado"
    )
    async def resultado(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        membro = interaction.user

        pode = (
            membro.guild_permissions.administrator
            or any(
                "mediador" in role.name.lower()
                or "staff" in role.name.lower()
                or "admin" in role.name.lower()
                for role in membro.roles
            )
        )

        if not pode:

            await interaction.response.send_message(
                "❌ Apenas mediadores podem registrar resultados.",
                ephemeral=True
            )

            return

        await interaction.response.send_modal(
            ResultadoModal(
                self.dono_id,
                self.valor
            )
        )


    @discord.ui.button(
        label="Fechar",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_fechar"
    )
    async def fechar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        membro = interaction.user

        pode = (
            membro.guild_permissions.administrator
            or any(
                "mediador" in role.name.lower()
                or "staff" in role.name.lower()
                or "admin" in role.name.lower()
                for role in membro.roles
            )
        )

        if not pode:

            await interaction.response.send_message(
                "❌ Apenas a equipe pode fechar.",
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            "🔒 Ticket fechado."
        )

        await interaction.channel.delete()


# ============================================================
# MODAL DA SALA
# ============================================================

class SalaModal(discord.ui.Modal):

    def __init__(self):

        super().__init__(
            title="Dados da Sala"
        )

        self.codigo = discord.ui.TextInput(
            label="Código da sala",
            placeholder="Ex: 123456",
            max_length=30
        )

        self.senha = discord.ui.TextInput(
            label="Senha",
            placeholder="Ex: 7890",
            max_length=30
        )

        self.add_item(self.codigo)
        self.add_item(self.senha)


    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        embed = discord.Embed(
            title="🔑 DADOS DA SALA",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Código",
            value=f"`{self.codigo.value}`",
            inline=False
        )

        embed.add_field(
            name="Senha",
            value=f"`{self.senha.value}`",
            inline=False
        )

        embed.set_footer(
            text="Sala criada pelo mediador"
        )

        await interaction.channel.send(
            embed=embed
        )

        await interaction.response.send_message(
            "✅ Dados enviados.",
            ephemeral=True
        )


# ============================================================
# MODAL DE RESULTADO
# ============================================================

class ResultadoModal(discord.ui.Modal):

    def __init__(
        self,
        jogador_id,
        valor
    ):

        super().__init__(
            title="Resultado da Partida"
        )

        self.jogador_id = jogador_id
        self.valor = valor

        self.vencedor = discord.ui.TextInput(
            label="ID do vencedor",
            placeholder="ID do Discord",
            max_length=30
        )

        self.add_item(self.vencedor)


    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        vencedor_id = self.vencedor.value

        try:
            vencedor_id = int(vencedor_id)
        except:

            await interaction.response.send_message(
                "❌ ID inválido.",
                ephemeral=True
            )

            return

        vencedor = interaction.guild.get_member(
            vencedor_id
        )

        if vencedor is None:

            await interaction.response.send_message(
                "❌ Jogador não encontrado no servidor.",
                ephemeral=True
            )

            return

        # Atualiza vencedor
        usuario = obter_usuario(vencedor.id)

        usuario["vitorias"] += 1
        usuario["partidas"] += 1

        # Atualiza dono do ticket se perdeu
        if vencedor.id != self.jogador_id:

            perdedor = obter_usuario(
                self.jogador_id
            )

            perdedor["derrotas"] += 1
            perdedor["partidas"] += 1

        salvar_dados(dados)

        embed = discord.Embed(
            title="🏆 RESULTADO FINAL",
            description=(
                f"🥇 **Vencedor:** {vencedor.mention}\n"
                f"💰 **Valor fictício:** {self.valor} créditos"
            ),
            color=discord.Color.gold()
        )

        await interaction.channel.send(
            embed=embed
        )

        await interaction.response.send_message(
            "✅ Resultado registrado.",
            ephemeral=True
        )


# ============================================================
# /PAINEL
# ============================================================

@bot.tree.command(
    name="painel",
    description="Envia o painel das salinhas"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def painel(
    interaction: discord.Interaction
):

    await interaction.channel.send(
        embed=embed_painel(),
        view=PainelView()
    )

    await interaction.response.send_message(
        "✅ Painel enviado.",
        ephemeral=True
    )


# ============================================================
# /SALDO
# ============================================================

@bot.tree.command(
    name="saldo",
    description="Mostra seus créditos fictícios"
)
async def saldo(
    interaction: discord.Interaction
):

    usuario = obter_usuario(
        interaction.user.id
    )

    embed = discord.Embed(
        title="💰 SEU SALDO",
        description=(
            f"👤 {interaction.user.mention}\n\n"
            f"💰 **{usuario['saldo']} créditos fictícios**"
        ),
        color=discord.Color.green()
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ============================================================
# /RANKING
# ============================================================

@bot.tree.command(
    name="ranking",
    description="Mostra o ranking dos jogadores"
)
async def ranking(
    interaction: discord.Interaction
):

    lista = []

    for user_id, info in dados["usuarios"].items():

        membro = interaction.guild.get_member(
            int(user_id)
        )

        if membro:

            lista.append(
                (
                    membro,
                    info["vitorias"]
                )
            )

    lista.sort(
        key=lambda x: x[1],
        reverse=True
    )

    texto = ""

    for posicao, (membro, vitorias) in enumerate(
        lista[:10],
        start=1
    ):

        texto += (
            f"**{posicao}.** "
            f"{membro.mention} — "
            f"🏆 {vitorias} vitórias\n"
        )

    if not texto:
        texto = "Nenhum jogador no ranking ainda."

    embed = discord.Embed(
        title="🏆 RANKING",
        description=texto,
        color=discord.Color.gold()
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# /REGRAS
# ============================================================

@bot.tree.command(
    name="regras",
    description="Mostra as regras"
)
async def regras(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="📜 REGRAS",
        description=(
            "1. Respeite todos os jogadores.\n"
            "2. Não utilize programas proibidos.\n"
            "3. Siga o modo escolhido.\n"
            "4. Respeite o mediador.\n"
            "5. Envie problemas pelo ticket.\n"
            "6. Os valores são apenas créditos fictícios.\n"
            "7. Nenhum crédito possui valor monetário real."
        ),
        color=discord.Color.blue()
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# /ADICIONAR_CREDITOS
# ============================================================

@bot.tree.command(
    name="adicionar_creditos",
    description="Adiciona créditos fictícios a um jogador"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def adicionar_creditos(
    interaction: discord.Interaction,
    jogador: discord.Member,
    quantidade: int
):

    if quantidade <= 0:

        await interaction.response.send_message(
            "❌ A quantidade precisa ser maior que 0.",
            ephemeral=True
        )

        return

    usuario = obter_usuario(
        jogador.id
    )

    usuario["saldo"] += quantidade

    salvar_dados(dados)

    await interaction.response.send_message(
        f"✅ {quantidade} créditos fictícios adicionados a "
        f"{jogador.mention}."
    )


# ============================================================
# /RESETAR
# ============================================================

@bot.tree.command(
    name="resetar",
    description="Reseta os dados de um jogador"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def resetar(
    interaction: discord.Interaction,
    jogador: discord.Member
):

    dados["usuarios"][str(jogador.id)] = {
        "saldo": 100,
        "vitorias": 0,
        "derrotas": 0,
        "partidas": 0
    }

    salvar_dados(dados)

    await interaction.response.send_message(
        f"🔄 Dados de {jogador.mention} resetados."
    )


# ============================================================
# EVENTO READY
# ============================================================

@bot.event
async def on_ready():

    # Comandos com botões persistentes
    bot.add_view(PainelView())

    print(
        f"✅ Bot conectado como {bot.user}"
    )

    try:

        synced = await bot.tree.sync()

        print(
            f"✅ {len(synced)} comandos sincronizados."
        )

    except Exception as erro:

        print(
            f"❌ Erro ao sincronizar comandos: {erro}"
        )


# ============================================================
# INICIAR
# ============================================================

if not TOKEN:

    print(
        "❌ TOKEN não encontrado no arquivo .env"
    )

else:

    bot.run(TOKEN)
