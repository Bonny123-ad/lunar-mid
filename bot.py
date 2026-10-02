
import os
import aiohttp
import discord

from decimal import Decimal, ROUND_HALF_UP
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PURINCASH_API_KEY = os.getenv("PURINCASH_API_KEY")
PURINCASH_BASE_URL = "https://api.purincash.com"

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


def dinheiro(valor):
    return Decimal(str(valor)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def para_centavos(valor):
    return int(dinheiro(valor) * 100)


def calcular_taxa(valor, modalidade):
    valor = dinheiro(valor)

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
        taxa = dinheiro(valor * Decimal("0.012"))

    if modalidade == "conta":
        taxa += dinheiro(valor * Decimal("0.05"))

    return dinheiro(taxa)


async def criar_cobranca_pix(valor_total, descricao):
    import logging

    logger = logging.getLogger("lunar_mid")

    if not PURINCASH_API_KEY:
        logger.error("PURINCASH_API_KEY não está configurada na hospedagem.")
        raise RuntimeError("A chave da PurinCash não está configurada.")

    url = f"{PURINCASH_BASE_URL}/v1/charges"
    headers = {
        "Authorization": f"Bearer {PURINCASH_API_KEY}",
        "Content-Type": "application/json",
    }
    dados = {
        "valueCents": para_centavos(valor_total),
        "description": str(descricao)[:200],
    }

    logger.info(
        "Solicitando cobrança PurinCash: valueCents=%s; descrição=%s",
        dados["valueCents"], dados["description"]
    )
    timeout = aiohttp.ClientTimeout(total=20)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as sessao:
            async with sessao.post(
                url, headers=headers, json=dados
            ) as resposta:
                texto = await resposta.text()
                logger.info("PurinCash respondeu HTTP %s.", resposta.status)

                if resposta.status not in (200, 201):
                    # A resposta detalhada fica apenas no console da hospedagem.
                    logger.error(
                        "Erro PurinCash HTTP %s; resposta: %s",
                        resposta.status, texto[:1000]
                    )
                    raise RuntimeError(
                        f"A PurinCash recusou a cobrança (HTTP {resposta.status}). "
                        "Consulte o console da hospedagem."
                    )

                try:
                    resultado = await resposta.json(content_type=None)
                except Exception as erro:
                    logger.error(
                        "PurinCash respondeu sucesso, mas não retornou JSON válido: %s",
                        texto[:500]
                    )
                    raise RuntimeError(
                        "A PurinCash retornou uma resposta inválida."
                    ) from erro

    except aiohttp.ClientError as erro:
        logger.exception("Falha de conexão com a PurinCash.")
        raise RuntimeError(
            "Não foi possível conectar à PurinCash. Confira o console."
        ) from erro

    if not isinstance(resultado, dict):
        logger.error("Resposta da PurinCash não é um objeto JSON.")
        raise RuntimeError("Resposta inválida da PurinCash.")

    pix = resultado.get("pix")
    pix = pix if isinstance(pix, dict) else {}
    payment_id = resultado.get("paymentId") or resultado.get("id")
    logger.info(
        "Resposta PurinCash: campos=%s; possui_id=%s; possui_codigo_pix=%s; status=%s",
        list(resultado.keys())[:30],
        bool(payment_id),
        bool(pix.get("brCode")),
        resultado.get("status", "não informado")
    )
    return resultado


def extrair_dados_pix(resultado):
    pix = resultado.get("pix")

    if not isinstance(pix, dict):
        pix = {}

    codigo = pix.get("brCode")
    imagem = pix.get("qrCodeImage")

    # Aceita somente um ID explicitamente retornado pela API.
    payment_id = (
        resultado.get("paymentId")
        or resultado.get("id")
    )

    return codigo, imagem, payment_id


def formatar_reais(valor):
    return f"R$ {dinheiro(valor):.2f}".replace(".", ",")


class FormularioNegociacao(
    discord.ui.Modal, title="Nova intermediação"
):
    produto = discord.ui.TextInput(
        label="Produto digital",
        placeholder="Descreva o produto",
        max_length=200,
    )

    valor = discord.ui.TextInput(
        label="Valor da negociação (R$)",
        placeholder="Ex.: 150,00",
        max_length=12,
    )

    def __init__(self, autor, outro, modalidade):
        super().__init__()
        self.autor = autor
        self.outro = outro
        self.modalidade = modalidade

    async def on_submit(self, interaction):
        texto_valor = str(self.valor.value).strip()
        texto_valor = texto_valor.replace("R$", "").replace(" ", "")

        # Aceita, por exemplo, 150,00 ou 150.00.
        if "," in texto_valor:
            texto_valor = texto_valor.replace(".", "").replace(",", ".")

        try:
            valor = dinheiro(texto_valor)

            if valor <= 0 or valor > Decimal("1000000"):
                raise ValueError

        except Exception:
            await interaction.response.send_message(
                "Digite um valor válido, por exemplo 150,00.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True, thinking=True
        )

        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                "Este comando só funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        categoria = discord.utils.get(
            guild.categories, name="Intermediações"
        )

        try:
            if categoria is None:
                categoria = await guild.create_category(
                    "Intermediações"
                )

            permissoes = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=False
                ),
                self.autor: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                ),
                self.outro: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                ),
            }

            if guild.me:
                permissoes[guild.me] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True,
                )

            for alvo, overwrite in categoria.overwrites.items():
                if (
                    isinstance(alvo, discord.Role)
                    and overwrite.view_channel is True
                ):
                    permissoes[alvo] = overwrite

            tipo = (
                "conta"
                if self.modalidade == "conta"
                else "pix"
            )

            canal = await guild.create_text_channel(
                name=f"mid-{tipo}-{self.autor.id}",
                category=categoria,
                overwrites=permissoes,
            )

        except discord.DiscordException:
            await interaction.followup.send(
                "Não consegui criar o canal. Verifique as permissões "
                "do bot no Discord.",
                ephemeral=True,
            )
            return

        taxa = calcular_taxa(valor, self.modalidade)
        total = dinheiro(valor + taxa)

        embed = discord.Embed(
            title="🌙 LUNAR MID — NOVA INTERMEDIAÇÃO",
            color=discord.Color.from_rgb(160, 32, 240),
        )

        embed.add_field(
            name="Modalidade",
            value=(
                "Middleman de Conta (PIX)"
                if tipo == "conta"
                else "Middleman de PIX"
            ),
            inline=False,
        )
        embed.add_field(
            name="Participante 1", value=self.autor.mention
        )
        embed.add_field(
            name="Participante 2", value=self.outro.mention
        )
        embed.add_field(
            name="Produto",
            value=self.produto.value,
            inline=False,
        )
        embed.add_field(
            name="Valor da negociação",
            value=formatar_reais(valor),
        )
        embed.add_field(
            name="Taxa do Lunar MID",
            value=formatar_reais(taxa),
        )
        embed.add_field(
            name="Total a pagar",
            value=formatar_reais(total),
            inline=False,
        )

        await canal.send(embed=embed)

        # Tenta criar a cobrança PIX na PurinCash.
        try:
            resultado = await criar_cobranca_pix(
                total,
                f"Lunar MID - {self.produto.value}",
            )

            codigo, imagem, payment_id = extrair_dados_pix(
                resultado
            )

            # Sem código PIX não há instrução de pagamento utilizável.
            if not codigo:
                await canal.send(
                    "⚠️ A PurinCash respondeu, mas não retornou "
                    "o código PIX esperado. A equipe deve verificar "
                    "a cobrança no painel do provedor antes de tentar "
                    "criar outra, para evitar duplicidade."
                )
            else:
                pix_embed = discord.Embed(
                    title="💜 Cobrança PIX",
                    description=(
                        f"**Total:** {formatar_reais(total)}\n\n"
                        "Use o código abaixo no aplicativo do seu banco. "
                        "Confira o valor e o destinatário antes de pagar."
                    ),
                    color=discord.Color.from_rgb(160, 32, 240),
                )

                pix_embed.add_field(
                    name="PIX copia e cola",
                    value=f"```text\n{codigo[:900]}\n```",
                    inline=False,
                )

                if payment_id:
                    pix_embed.add_field(
                        name="Referência da cobrança",
                        value=str(payment_id)[:200],
                        inline=False,
                    )

                if imagem:
                    # QR codes podem vir como URL ou data URI.
                    # Não incorporamos conteúdo arbitrário retornado
                    # pela API; por enquanto mostramos o copia e cola.
                    pix_embed.set_footer(
                        text="Use o código PIX copia e cola acima."
                    )

                await canal.send(embed=pix_embed)

                await canal.send(
                    "⚠️ Esta versão ainda não confirma automaticamente "
                    "o pagamento. Não considere a negociação paga até "
                    "que o status seja verificado diretamente na PurinCash."
                )

        except (aiohttp.ClientError, TimeoutError, RuntimeError) as erro:
            print(f"Erro na integração PurinCash: {erro}")

            await canal.send(
                "⚠️ Não consegui confirmar a criação da cobrança PIX. "
                "Não tente pagar por um código antigo nem crie outra "
                "cobrança sem verificar o painel da PurinCash."
            )

        await interaction.followup.send(
            f"Canal privado criado: {canal.mention}",
            ephemeral=True,
        )


class SelecionarPessoa(discord.ui.UserSelect):
    def __init__(self, modalidade):
        super().__init__(
            placeholder="Selecione a outra pessoa da negociação",
            min_values=1,
            max_values=1,
        )
        self.modalidade = modalidade

    async def callback(self, interaction):
        outro = self.values[0]

        if outro.id == interaction.user.id:
            await interaction.response.send_message(
                "Escolha outra pessoa!", ephemeral=True
            )
            return

        if outro.bot:
            await interaction.response.send_message(
                "Escolha um membro, não um bot!", ephemeral=True
            )
            return

        await interaction.response.send_modal(
            FormularioNegociacao(
                interaction.user, outro, self.modalidade
            )
        )


class EscolherPessoa(discord.ui.View):
    def __init__(self, modalidade):
        super().__init__(timeout=180)
        self.add_item(SelecionarPessoa(modalidade))


class MenuModalidade(discord.ui.Select):
    def __init__(self):
        opcoes = [
            discord.SelectOption(
                label="Middleman de PIX",
                description="Negociações sem contas, conforme as regras.",
                emoji="💜",
                value="pix",
            ),
            discord.SelectOption(
                label="Middleman de Conta (PIX)",
                description="Negociações envolvendo contas digitais.",
                emoji="💎",
                value="conta",
            ),
        ]

        super().__init__(
            placeholder="Selecione o tipo de intermediação",
            min_values=1,
            max_values=1,
            options=opcoes,
            custom_id="lunar_mid:modalidade",
        )

    async def callback(self, interaction):
        await interaction.response.send_message(
            "🤝 **Agora escolha a outra pessoa da negociação:**",
            view=EscolherPessoa(self.values[0]),
            ephemeral=True,
        )


class PainelIntermediacao(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MenuModalidade())


@bot.tree.command(
    name="painelmid",
    description="Publica o painel de intermediação Lunar MID",
)
@app_commands.guild_only()
async def painelmid(interaction):
    embed = discord.Embed(
        title="🌙 LUNAR MID — CENTRAL DE INTERMEDIAÇÃO",
        description=(
            "Bem-vindo ao sistema de intermediação Lunar MID!\n"
            "Selecione a modalidade no menu abaixo e siga as etapas "
            "para abrir seu canal privado."
        ),
        color=discord.Color.from_rgb(160, 32, 240),
    )

    embed.add_field(
        name="💜 Middleman de PIX",
        value="Para negociações sem contas, conforme as regras do servidor.",
        inline=False,
    )
    embed.add_field(
        name="💎 Middleman de Conta (PIX)",
        value=(
            "Para negociações envolvendo contas digitais. "
            "Aplica-se a taxa adicional de 5%, conforme as regras."
        ),
        inline=False,
    )
    embed.add_field(
        name="📋 Tabela de taxas",
        value=(
            "Até R$ 2,50: sem taxa fixa\n"
            "Acima de R$ 2,50 até R$ 100: R$ 1,20\n"
            "Acima de R$ 100 até R$ 200: R$ 2,50\n"
            "Acima de R$ 200 até R$ 400: R$ 5,00\n"
            "Acima de R$ 400 até R$ 700: R$ 8,00\n"
            "Acima de R$ 700: 1,2%\n\n"
            "Negociações com contas: +5% de taxa."
        ),
        inline=False,
    )
    embed.set_footer(
        text="Lunar MID • Negocie com atenção e segurança"
    )

    await interaction.response.send_message(
        embed=embed,
        view=PainelIntermediacao(),
    )


@bot.event
async def on_ready():
    bot.add_view(PainelIntermediacao())
    print(f"🌙 Lunar MID conectado como {bot.user}!")

    try:
        await bot.tree.sync()
        print("Comando /painelmid sincronizado!")
    except Exception as erro:
        print(f"Erro ao sincronizar comandos: {erro}")


if not TOKEN:
    raise RuntimeError("Token DISCORD_TOKEN não configurado.")

bot.run(TOKEN)
