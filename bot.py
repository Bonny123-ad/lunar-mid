import discord
from discord.ext import commands
import asyncio
import random

# Configuração de intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Configuração da Chave PIX da sua Organização
CHAVE_PIX = "sua-chave-pix-aqui@email.com"
NOME_TITULAR = "Nome do Dono / Organização FF"

class FilaModal(discord.ui.Modal, title="Confirmação de Inscrição"):
    nick_ff = discord.ui.TextInput(
        label="Seu Nick no Free Fire",
        placeholder="Ex: LOUD CORINGA",
        required=True,
        max_length=50
    )
    id_ff = discord.ui.TextInput(
        label="Seu ID do Free Fire",
        placeholder="Ex: 123456789",
        required=True,
        max_length=20
    )

    def __init__(self, formato: str, valor: float, regra: str):
        super().__init__()
        self.formato = formato
        self.valor = valor
        self.regra = regra

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user

        # Criar categoria de tickets se não existir (ou usar uma específica)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        # Dar permissão para a staff ver o ticket (substitua 'Cargo Staff' pelo nome do cargo no seu servidor)
        staff_role = discord.utils.get(guild.roles, name="Staff")
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # Criar o canal de ticket privado
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{member.name}",
            overwrites=overwrites,
            topic=f"Aposta FF - {self.formato} | Valor: R$ {self.valor:.2f} | Jogador: {self.nick_ff.value} ({self.id_ff.value})"
        )

        # Embed de Cobrança PIX dentro do Ticket
        embed_pix = discord.Embed(
            title="💰 Pagamento da Aposta - Free Fire",
            description=f"Olá **{member.mention}**, você entrou na fila para a modalidade **{self.formato}** com a regra **{self.regra}**.",
            color=discord.Color.green()
        )
        embed_pix.add_field(name="💳 Valor da Inscrição", value=f"`R$ {self.valor:.2f}`", inline=False)
        embed_pix.add_field(name="📍 Chave PIX (E-mail/Aleatória)", value=f"`{CHAVE_PIX}`\nTitular: {NOME_TITULAR}", inline=False)
        embed_pix.add_field(name="⚠️ Instruções", value="1. Faça o PIX do valor exato.\n2. Envie o **comprovante em anexo** neste chat.\n3. Aguarde a confirmação da staff para receber a sala e senha.", inline=False)
        embed_pix.set_footer(text="O canal será fechado após a confirmação.")

        await ticket_channel.send(content=f"{member.mention} <@&{staff_role.id}> se necessário!", embed=embed_pix)

        # Resposta privada para o usuário avisando que o ticket foi aberto
        await interaction.response.send_message(
            f"✅ Inscrição realizada com sucesso! Um ticket privado foi aberto para você: {ticket_channel.mention}", 
            ephemeral=True
        )

class SalaView(discord.ui.View):
    def __init__(self, formato: str, valor: float):
        super().__init__(timeout=None)
        self.formato = formato
        self.valor = valor

    @discord.ui.button(label="Normal", style=discord.ButtonStyle.primary, custom_id="btn_normal")
    async def btn_normal(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = FilaModal(formato=self.formato, valor=self.valor, regra="Normal")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Full Ump / Xm8", style=discord.ButtonStyle.danger, custom_id="btn_ump")
    async def btn_ump(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = FilaModal(formato=self.formato, valor=self.valor, regra="Full Ump / Xm8")
        await interaction.response.send_modal(modal)

@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user} (ID: {bot.user.id})")
    print("Bot pronto para gerenciar salas de apostas de Free Fire!")

@bot.command(name="criarsala")
@commands.has_permissions(administrator=True)
async def criarsala(ctx, formato: str, valor: float):
    """Comando para a staff criar um painel de sala. Ex: !criarsala "2v2 Mobile" 10.00"""
    if valor < 0.10 or valor > 100.00:
        await ctx.send("❌ O valor da aposta deve ser entre **R$ 0,10** e **R$ 100,00**.")
        return

    embed = discord.Embed(
        title=f"🔥 SALA DE APOSTA FF - {formato.upper()} 🔥",
        description="Clique em um dos botões abaixo de acordo com a regra desejada para entrar na fila e abrir seu ticket de pagamento.",
        color=discord.Color.from_rgb(255, 100, 0)
    )
    embed.add_field(name="🎮 Formato", value=formato, inline=True)
    embed.add_field(name="💵 Valor da Aposta", value=f"R$ {valor:.2f}", inline=True)
    embed.add_field(name="👥 Status", value="Aguardando jogadores...", inline=False)
    embed.set_footer(text="Organização de Free Fire • Sistema Automatizado")

    view = SalaView(formato=formato, valor=valor)
    await ctx.send(embed=embed, view=view)
    # Deleta a mensagem do comando digitado pela staff para manter o chat limpo
    try:
        await ctx.message.delete()
    except:
        pass

# Insira o token do seu bot do Discord Developer Portal aqui
bot.run("SEU_TOKEN_DO_BOT_AQUI")
