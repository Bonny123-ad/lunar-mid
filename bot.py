
import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


def calcular_taxa(valor, modalidade):
    if valor <= 2.50:
        taxa = 0.0
    elif valor <= 100:
        taxa = 1.20
    elif valor <= 200:
        taxa = 2.50
    elif valor <= 400:
        taxa = 5.00
    elif valor <= 700:
        taxa = 8.00
    else:
        taxa = valor * 0.012

    if modalidade == "conta":
        taxa += valor * 0.05

    return round(taxa, 2)


class FormularioNegociacao(discord.ui.Modal, title="Nova intermediação"):
    produto = discord.ui.TextInput(
        label="Produto digital",
        placeholder="Descreva o produto",
        max_length=200
    )
    valor = discord.ui.TextInput(
        label="Valor da negociação (R$)",
        placeholder="Ex.: 150,00",
        max_length=12
    )

    def __init__(self, autor, outro, modalidade):
        super().__init__()
        self.autor = autor
        self.outro = outro
        self.modalidade = modalidade

    async def on_submit(self, interaction):
        try:
            valor = float(str(self.valor.value).replace(",", "."))
            if valor <= 0 or valor > 1000000:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Digite um valor válido, por exemplo 150,00.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = interaction.guild
        categoria = discord.utils.get(
            guild.categories, name="Intermediações"
        )
        if categoria is None:
            categoria = await guild.create_category("Intermediações")

        permissoes = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            self.autor: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
            self.outro: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
        }

        if guild.me:
            permissoes[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True
            )

        # Mantém visíveis os cargos que já têm acesso à categoria.
        for alvo, overwrite in categoria.overwrites.items():
            if isinstance(alvo, discord.Role) and overwrite.view_channel is True:
                permissoes[alvo] = overwrite

        tipo = "conta" if self.modalidade == "conta" else "pix"
        canal = await guild.create_text_channel(
            name=f"mid-{tipo}-{self.autor.id}",
            category=categoria,
            overwrites=permissoes
        )

        taxa = calcular_taxa(valor, self.modalidade)
        embed = discord.Embed(
            title="🌙 LUNAR MID — NOVA INTERMEDIAÇÃO",
            color=discord.Color.from_rgb(160, 32, 240)
        )
        embed.add_field(
            name="Modalidade",
            value="Middleman de Conta (PIX)" if tipo == "conta"
            else "Middleman de PIX",
            inline=False
        )
        embed.add_field(name="Participante 1", value=self.autor.mention)
        embed.add_field(name="Participante 2", value=self.outro.mention)
        embed.add_field(name="Produto", value=self.produto.value, inline=False)
        embed.add_field(name="Valor informado", value=f"R$ {valor:.2f}")
        embed.add_field(name="Taxa estimada", value=f"R$ {taxa:.2f}")
        embed.add_field(
            name="Valor após taxa",
            value=f"R$ {valor - taxa:.2f}"
        )
        embed.add_field(
            name="Próximas etapas",
            value=(
                "1. Confirmem os detalhes da negociação.\n"
                "2. O responsável verifica o recebimento.\n"
                "3. O comprador confirma a entrega.\n\n"
                "⚠️ Não compartilhem senhas ou códigos de acesso.\n"
                "O bot ainda não confirma PIX nem realiza repasses."
            ),
            inline=False
        )
        await canal.send(embed=embed)

        await interaction.followup.send(
            f"Canal privado criado: {canal.mention}",
            ephemeral=True
        )


class SelecionarPessoa(discord.ui.UserSelect):
    def __init__(self, modalidade):
        super().__init__(
            placeholder="Selecione a outra pessoa da negociação",
            min_values=1,
            max_values=1
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
                value="pix"
            ),
            discord.SelectOption(
                label="Middleman de Conta (PIX)",
                description="Negociações envolvendo contas digitais.",
                emoji="💎",
                value="conta"
            )
        ]
        super().__init__(
            placeholder="Selecione o tipo de intermediação",
            min_values=1,
            max_values=1,
            options=opcoes,
            custom_id="lunar_mid:modalidade"
        )

    async def callback(self, interaction):
        await interaction.response.send_message(
            "🤝 **Agora escolha a outra pessoa da negociação:**",
            view=EscolherPessoa(self.values[0]),
            ephemeral=True
        )


class PainelIntermediacao(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MenuModalidade())


@bot.tree.command(
    name="painelmid",
    description="Publica o painel de intermediação Lunar MID"
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
        color=discord.Color.from_rgb(160, 32, 240)
    )
    embed.add_field(
        name="💜 Middleman de PIX",
        value="Para negociações sem contas, conforme as regras do servidor.",
        inline=False
    )
    embed.add_field(
        name="💎 Middleman de Conta (PIX)",
        value="Para negociações envolvendo contas digitais. "
              "Aplica-se a taxa adicional de 5%, conforme as regras.",
        inline=False
    )
    embed.add_field(
        name="📋 Tabela de taxas",
        value=(
            "R$ 1,20 — acima de R$ 2,50\n"
            "R$ 2,50 — acima de R$ 100,00\n"
            "R$ 5,00 — acima de R$ 200,00\n"
            "R$ 8,00 — acima de R$ 400,00\n"
            "1,2% — acima de R$ 700,00\n\n"
            "Negociações com contas: +5% de taxa.\n"
            "A regra de exceção para contas de Roblox sem e-mail "
            "precisa ser aplicada conforme confirmação da equipe."
        ),
        inline=False
    )
    embed.set_footer(text="Lunar MID • Negocie com atenção e segurança")

    await interaction.response.send_message(
        embed=embed,
        view=PainelIntermediacao()
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
    raise RuntimeError("Token não encontrado no arquivo .env")

bot.run(TOKEN)