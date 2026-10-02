import os
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# Configure these in FadeHost -> Environment Variables.
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0") or 0)
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "0") or 0)
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0") or 0)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("lunar_mid")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


def dinheiro(valor: Decimal) -> str:
    return f"R${valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def calcular_taxa(valor: Decimal, modalidade: str = "produto") -> Decimal:
    if valor <= Decimal("2.50"):
        taxa = Decimal("0.00")
    elif valor <= Decimal("100"):
        taxa = Decimal("1.20")
    elif valor <= Decimal("200"):
        taxa = Decimal("2.50")
    elif valor <= Decimal("400"):
        taxa = Decimal("5.00")
    elif valor <= Decimal("700"):
        taxa = Decimal("8.00")
    else:
        taxa = (valor * Decimal("0.012")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if modalidade.lower() == "conta":
        taxa += (valor * Decimal("0.05")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return taxa.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def registrar(guild: discord.Guild, mensagem: str):
    if LOG_CHANNEL_ID:
        canal = guild.get_channel(LOG_CHANNEL_ID)
        if isinstance(canal, discord.TextChannel):
            try:
                await canal.send(mensagem)
            except discord.HTTPException:
                pass


def embed_base(titulo: str, descricao: str = "") -> discord.Embed:
    e = discord.Embed(title=titulo, description=descricao, color=discord.Color.from_rgb(139, 92, 246))
    e.set_footer(text="Lunar MID • Mediação manual")
    return e


class AbrirTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir mediação", style=discord.ButtonStyle.primary, emoji="🌙", custom_id="lunar_mid:abrir")
    async def abrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use este botão dentro do servidor.", ephemeral=True)

        guild = interaction.guild
        categoria = guild.get_channel(TICKET_CATEGORY_ID) if TICKET_CATEGORY_ID else None
        if categoria is not None and not isinstance(categoria, discord.CategoryChannel):
            categoria = None

        nome = f"mid-{interaction.user.name}".lower().replace(" ", "-")[:90]
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True),
        }
        if STAFF_ROLE_ID:
            cargo = guild.get_role(STAFF_ROLE_ID)
            if cargo:
                overwrites[cargo] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)

        try:
            canal = await guild.create_text_channel(
                name=nome,
                category=categoria,
                overwrites=overwrites,
                topic=f"Lunar MID | responsável: {interaction.user.id} | participante ainda não escolhido",
                reason="Abertura de ticket Lunar MID",
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "Não tenho permissão para criar canais. Dê ao bot Gerenciar Canais e confira as permissões da categoria.",
                ephemeral=True,
            )

        await interaction.response.send_message(f"Seu ticket foi criado: {canal.mention}", ephemeral=True)
        aviso = embed_base(
            "Sistema de Mediação",
            "Pedido de intermediação criado com sucesso!\n\n"
            "A negociação deve acontecer exclusivamente neste ticket. "
            "A equipe e o bot nunca pedirão sua senha ou códigos de autenticação.",
        )
        aviso.add_field(name="Ticket", value=canal.mention, inline=False)
        aviso.add_field(
            name="Notificação de Segurança",
            value="Confira os dados antes de prosseguir. Não considere um pagamento concluído apenas por prints. "
                  "A equipe não garante transações feitas fora deste ticket.",
            inline=False,
        )
        await canal.send(content=interaction.user.mention, embed=aviso)
        await canal.send("**1/5 — Com quem você está negociando?** Selecione a outra pessoa abaixo.", view=EscolherParticipanteView(interaction.user.id))
        await registrar(guild, f"🌙 Ticket aberto: {canal.mention} por {interaction.user.mention}")

class EscolherParticipanteView(discord.ui.View):
    def __init__(self, criador_id: int):
        super().__init__(timeout=3600)
        self.criador_id = criador_id

    @discord.ui.user_select(placeholder="Selecionar usuário", min_values=1, max_values=1)
    async def selecionar(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if interaction.user.id != self.criador_id:
            return await interaction.response.send_message("Só quem abriu o ticket pode escolher o participante.", ephemeral=True)
        participante = select.values[0]
        if participante.id == self.criador_id or participante.bot:
            return await interaction.response.send_message("Escolha outra pessoa, que não seja você nem um bot.", ephemeral=True)
        canal = interaction.channel
        if not isinstance(canal, discord.TextChannel):
            return await interaction.response.send_message("Canal inválido.", ephemeral=True)
        try:
            await canal.set_permissions(participante, view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)
            await canal.edit(topic=f"Lunar MID | criador: {self.criador_id} | participante: {participante.id}")
        except discord.Forbidden:
            return await interaction.response.send_message("Não consigo atualizar as permissões deste canal.", ephemeral=True)

        estado = EstadoNegociacao(canal.id, self.criador_id, participante.id)
        ESTADOS[canal.id] = estado
        await interaction.response.send_message(f"Participante escolhido: {participante.mention}", ephemeral=True)
        await canal.send(
            embed=embed_base("Atribuição de Função", "Cada pessoa deve escolher o papel que corresponde à negociação."),
            view=PapeisView(canal.id),
        )
        await registrar(interaction.guild, f"👥 Participantes no ticket {canal.mention}: <@{self.criador_id}> e {participante.mention}")


class EstadoNegociacao:
    def __init__(self, canal_id: int, criador_id: int, participante_id: int):
        self.canal_id = canal_id
        self.criador_id = criador_id
        self.participante_id = participante_id
        self.papeis: dict[int, str] = {}
        self.valor: Decimal | None = None
        self.modalidade = "produto"
        self.confirmacoes: set[int] = set()
        self.etapa = "papeis"


ESTADOS: dict[int, EstadoNegociacao] = {}


def estado_do(interaction: discord.Interaction) -> EstadoNegociacao | None:
    return ESTADOS.get(interaction.channel_id or 0)


class PapeisView(discord.ui.View):
    def __init__(self, canal_id: int):
        super().__init__(timeout=86400)
        self.canal_id = canal_id

    async def escolher(self, interaction: discord.Interaction, papel: str):
        estado = ESTADOS.get(self.canal_id)
        if not estado or interaction.user.id not in (estado.criador_id, estado.participante_id):
            return await interaction.response.send_message("Você não faz parte desta negociação.", ephemeral=True)
        estado.papeis[interaction.user.id] = papel
        await interaction.response.send_message(f"Papel registrado: **{papel}**.", ephemeral=True)
        if estado.criador_id in estado.papeis and estado.participante_id in estado.papeis:
            if estado.papeis[estado.criador_id] == estado.papeis[estado.participante_id]:
                estado.papeis.pop(interaction.user.id, None)
                return await interaction.followup.send("Os participantes precisam escolher papéis diferentes. Escolha novamente.", ephemeral=True)
            estado.etapa = "valor"
            canal = interaction.guild.get_channel(estado.canal_id) if interaction.guild else None
            if isinstance(canal, discord.TextChannel):
                await canal.send(
                    embed=embed_base("Confirmar valor", "Informe o valor combinado. Os dois participantes terão que confirmar."),
                    view=ProporValorView(self.canal_id),
                )
                await registrar(interaction.guild, f"🧭 Papéis definidos no ticket {canal.mention}.")

    @discord.ui.button(label="Enviando", style=discord.ButtonStyle.primary, emoji="📤", custom_id="lunar_mid:enviando")
    async def enviando(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.escolher(interaction, "Enviando")

    @discord.ui.button(label="Recebendo", style=discord.ButtonStyle.secondary, emoji="📥", custom_id="lunar_mid:recebendo")
    async def recebendo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.escolher(interaction, "Recebendo")


class ValorModal(discord.ui.Modal, title="Propor valor da negociação"):
    valor = discord.ui.TextInput(label="Valor combinado (R$)", placeholder="Ex.: 50,00", max_length=15)
    modalidade = discord.ui.TextInput(label="Tipo (produto ou conta)", placeholder="produto", default="produto", max_length=15, required=True)

    def __init__(self, canal_id: int):
        super().__init__()
        self.canal_id = canal_id

    async def on_submit(self, interaction: discord.Interaction):
        estado = ESTADOS.get(self.canal_id)
        if not estado or interaction.user.id not in (estado.criador_id, estado.participante_id):
            return await interaction.response.send_message("Você não faz parte desta negociação.", ephemeral=True)
        raw = str(self.valor.value).strip().replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
        try:
            valor = Decimal(raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if valor <= 0 or valor > Decimal("1000000"):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            return await interaction.response.send_message("Digite um valor válido, por exemplo `50,00`.", ephemeral=True)
        modalidade = str(self.modalidade.value).strip().lower()
        if modalidade not in ("produto", "conta"):
            return await interaction.response.send_message("O tipo precisa ser `produto` ou `conta`.", ephemeral=True)
        estado.valor = valor
        estado.modalidade = modalidade
        estado.confirmacoes.clear()
        estado.etapa = "confirmar_valor"
        taxa = calcular_taxa(valor, modalidade)
        total = valor + taxa
        canal = interaction.guild.get_channel(self.canal_id) if interaction.guild else None
        await interaction.response.send_message("Proposta publicada no ticket. As confirmações anteriores foram zeradas.", ephemeral=True)
        if isinstance(canal, discord.TextChannel):
            await canal.send(
                embed=embed_base(
                    "Confirmar valor",
                    f"**Valor proposto:** {dinheiro(valor)}\n"
                    f"**Taxa estimada:** {dinheiro(taxa)}\n"
                    f"**Total com taxa:** {dinheiro(total)}\n\n"
                    f"**Confirmações:** <@{estado.criador_id}> ⏳ • <@{estado.participante_id}> ⏳\n"
                    "Ambos devem clicar em **Confirmar valor**. Editar a proposta reinicia as confirmações.",
                ),
                view=ConfirmarValorView(self.canal_id),
            )
            await registrar(interaction.guild, f"💰 Proposta de {dinheiro(valor)} no ticket {canal.mention}; aguardando duas confirmações.")


class ProporValorView(discord.ui.View):
    def __init__(self, canal_id: int):
        super().__init__(timeout=86400)
        self.canal_id = canal_id

    @discord.ui.button(label="Definir valor", style=discord.ButtonStyle.primary, emoji="💵", custom_id="lunar_mid:definir_valor")
    async def definir(self, interaction: discord.Interaction, button: discord.ui.Button):
        estado = ESTADOS.get(self.canal_id)
        if not estado or interaction.user.id not in (estado.criador_id, estado.participante_id):
            return await interaction.response.send_message("Você não faz parte desta negociação.", ephemeral=True)
        await interaction.response.send_modal(ValorModal(self.canal_id))


class ConfirmarValorView(discord.ui.View):
    def __init__(self, canal_id: int):
        super().__init__(timeout=86400)
        self.canal_id = canal_id

    @discord.ui.button(label="Confirmar valor", style=discord.ButtonStyle.success, emoji="✅", custom_id="lunar_mid:confirmar_valor")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        estado = ESTADOS.get(self.canal_id)
        if not estado or estado.valor is None:
            return await interaction.response.send_message("Não há uma proposta ativa.", ephemeral=True)
        if interaction.user.id not in (estado.criador_id, estado.participante_id):
            return await interaction.response.send_message("Só os participantes podem confirmar.", ephemeral=True)
        estado.confirmacoes.add(interaction.user.id)
        await interaction.response.send_message("Sua confirmação foi registrada.", ephemeral=True)
        if estado.criador_id in estado.confirmacoes and estado.participante_id in estado.confirmacoes:
            estado.etapa = "negociacao"
            canal = interaction.guild.get_channel(self.canal_id) if interaction.guild else None
            if isinstance(canal, discord.TextChannel):
                taxa = calcular_taxa(estado.valor, estado.modalidade)
                await canal.send(
                    embed=embed_base(
                        "Valor confirmado pelas duas partes",
                        f"**Valor:** {dinheiro(estado.valor)}\n**Taxa:** {dinheiro(taxa)}\n"
                        f"**Total:** {dinheiro(estado.valor + taxa)}\n\n"
                        "As duas partes confirmaram a proposta. A partir daqui, continuem a negociação neste ticket. "
                        "A confirmação do valor **não significa que houve pagamento**.",
                    ),
                    view=EtapasManuaisView(self.canal_id),
                )
                await registrar(interaction.guild, f"✅ Valor confirmado pelas duas partes no ticket {canal.mention}.")
                self.disable_all_items()
                try:
                    await interaction.message.edit(view=self)
                except discord.HTTPException:
                    pass

    @discord.ui.button(label="Editar valor", style=discord.ButtonStyle.secondary, emoji="🖊️", custom_id="lunar_mid:editar_valor")
    async def editar(self, interaction: discord.Interaction, button: discord.ui.Button):
        estado = ESTADOS.get(self.canal_id)
        if not estado or interaction.user.id not in (estado.criador_id, estado.participante_id):
            return await interaction.response.send_message("Só os participantes podem editar a proposta.", ephemeral=True)
        await interaction.response.send_modal(ValorModal(self.canal_id))


class EtapasManuaisView(discord.ui.View):
    def __init__(self, canal_id: int):
        super().__init__(timeout=86400)
        self.canal_id = canal_id

    async def marcar(self, interaction: discord.Interaction, chave: str, titulo: str):
        estado = ESTADOS.get(self.canal_id)
        if not estado or interaction.user.id not in (estado.criador_id, estado.participante_id):
            return await interaction.response.send_message("Só os participantes podem usar esta etapa.", ephemeral=True)
        estado.etapa = chave
        await interaction.response.send_message(f"Etapa registrada manualmente: **{titulo}**. Isso não verifica nem comprova pagamento.", ephemeral=True)
        canal = interaction.guild.get_channel(self.canal_id) if interaction.guild else None
        if isinstance(canal, discord.TextChannel):
            await canal.send(f"📝 {interaction.user.mention} marcou a etapa **{titulo}**. Esta marcação é manual e não comprova pagamento.")
            await registrar(interaction.guild, f"📝 {titulo} marcado por {interaction.user.mention} em {canal.mention}.")

    @discord.ui.button(label="Dinheiro enviado", style=discord.ButtonStyle.primary, emoji="📤", custom_id="lunar_mid:dinheiro_enviado")
    async def enviado(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.marcar(interaction, "enviado_manual", "Dinheiro enviado (declaração manual)")

    @discord.ui.button(label="Recebimento confirmado", style=discord.ButtonStyle.success, emoji="📥", custom_id="lunar_mid:recebimento")
    async def recebido(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.marcar(interaction, "recebido_manual", "Recebimento confirmado (declaração manual)")

    @discord.ui.button(label="Encerrar ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="lunar_mid:encerrar")
    async def encerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Canal inválido.", ephemeral=True)
        membro = interaction.user if isinstance(interaction.user, discord.Member) else None
        permitido = membro and (membro.guild_permissions.manage_channels or interaction.user.id in (
            ESTADOS.get(self.canal_id).criador_id if ESTADOS.get(self.canal_id) else -1,
            ESTADOS.get(self.canal_id).participante_id if ESTADOS.get(self.canal_id) else -1,
        ))
        if not permitido:
            return await interaction.response.send_message("Somente os participantes ou a equipe podem encerrar.", ephemeral=True)
        await interaction.response.send_message("Ticket será fechado em 5 segundos.", ephemeral=True)
        await interaction.channel.send("🔒 Ticket encerrado manualmente. Guarde o histórico da negociação.")
        await registrar(interaction.guild, f"🔒 Ticket encerrado: {interaction.channel.name} por {interaction.user.mention}")
        await discord.utils.sleep_until(discord.utils.utcnow() + __import__("datetime").timedelta(seconds=5))
        try:
            await interaction.channel.delete(reason=f"Ticket encerrado por {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send("Não tenho permissão para excluir o canal. Confira Gerenciar Canais.", ephemeral=True)


@bot.event
async def on_ready():
    log.info("Conectado como %s", bot.user)
    try:
        synced = await bot.tree.sync()
        log.info("Comandos sincronizados: %s", len(synced))
    except Exception:
        log.exception("Falha ao sincronizar comandos")


@bot.tree.command(name="painelmid", description="Publica o painel para abrir uma mediação Lunar MID")
@app_commands.default_permissions(manage_guild=True)
async def painelmid(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("Use este comando dentro de um servidor.", ephemeral=True)
    embed = embed_base(
        "🌙 Lunar MID • Sistema de Mediação",
        "Abra um ticket para iniciar uma negociação com outra pessoa.\n\n"
        "• Escolha o outro participante\n"
        "• Definam os papéis e o valor\n"
        "• Ambos confirmam a proposta\n"
        "• Sigam as etapas manualmente dentro do ticket\n\n"
        "⚠️ Confirmações manuais não comprovam pagamentos. Não compartilhe senhas, códigos de autenticação ou dados bancários no ticket.",
    )
    await interaction.response.send_message("Painel publicado.", ephemeral=True)
    await interaction.channel.send(embed=embed, view=AbrirTicketView())


@bot.tree.command(name="midajuda", description="Mostra as instruções do Lunar MID")
async def midajuda(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=embed_base(
            "Ajuda • Lunar MID",
            "Use `/painelmid` (permissão Gerenciar Servidor) para publicar o painel.\n"
            "Configure `TICKET_CATEGORY_ID`, `STAFF_ROLE_ID` e `LOG_CHANNEL_ID` como variáveis opcionais na hospedagem.\n"
            "O bot não processa pagamentos nem verifica PIX automaticamente nesta versão.",
        ),
        ephemeral=True,
    )


if not TOKEN:
    raise RuntimeError("Configure a variável de ambiente DISCORD_TOKEN na FadeHost.")
bot.run(TOKEN)
