import os
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import aiosqlite

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0")) or None
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "0")) or None
DATABASE_PATH = os.getenv("DATABASE_PATH", "lunar_org.db")

if not TOKEN:
    raise RuntimeError("Defina DISCORD_TOKEN no arquivo .env.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("lunar_org")

intents = discord.Intents.default()
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
db: Optional[aiosqlite.Connection] = None

PURPLE = 0x7B2CFF
DARK = 0x17131F
RED = 0xE5484D
GREEN = 0x31B77A


def is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    ids = {rid for rid in (ADMIN_ROLE_ID, STAFF_ROLE_ID) if rid}
    return any(role.id in ids for role in member.roles)


async def audit(guild: discord.Guild, action: str, actor: str, details: str = ""):
    channel_id = int(os.getenv("LOG_CHANNEL_ID", "0"))
    channel = guild.get_channel(channel_id) if channel_id else None
    if isinstance(channel, discord.TextChannel):
        embed = discord.Embed(title=f"Registro • {action}", description=details or "—",
                              color=PURPLE, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Responsável", value=actor, inline=True)
        await channel.send(embed=embed)


async def init_db():
    global db
    db = await aiosqlite.connect(DATABASE_PATH)
    await db.execute("""CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER,
        game_name TEXT, game_uid TEXT, role TEXT, status TEXT DEFAULT 'Pendente',
        created_at TEXT)""")
    await db.execute("""CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, name TEXT,
        captain_id INTEGER, roster TEXT DEFAULT '', created_at TEXT)""")
    await db.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, title TEXT,
        kind TEXT, description TEXT, created_by INTEGER, created_at TEXT)""")
    await db.execute("""CREATE TABLE IF NOT EXISTS attendance (
        event_id INTEGER, user_id INTEGER, status TEXT,
        PRIMARY KEY(event_id, user_id))""")
    await db.execute("""CREATE TABLE IF NOT EXISTS sanctions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER,
        moderator_id INTEGER, kind TEXT, reason TEXT, created_at TEXT)""")
    await db.commit()


def main_embed():
    e = discord.Embed(
        title="🌙 LUNAR O.R.G • Central da Organização",
        description=("Bem-vindo à central oficial da **Lunar O.R.G**.\n"
                     "Use os painéis abaixo para se recrutar, organizar times e acompanhar os treinos.\n\n"
                     "🟣 **Tema:** roxo e preto\n"
                     "⚫ **Conduta:** respeito, fair play e compromisso."),
        color=PURPLE
    )
    e.set_footer(text="Lunar O.R.G • Free Fire")
    return e


class RecruitmentModal(discord.ui.Modal, title="Recrutamento • Lunar O.R.G"):
    nick = discord.ui.TextInput(label="Nick no Free Fire", max_length=32, placeholder="Seu nick")
    uid = discord.ui.TextInput(label="ID do jogador", max_length=24, placeholder="Seu ID numérico")
    role = discord.ui.TextInput(label="Função desejada", max_length=40, placeholder="Rush, suporte, IGL...")
    age = discord.ui.TextInput(label="Idade", max_length=2, placeholder="Idade")
    availability = discord.ui.TextInput(label="Disponibilidade / experiência", style=discord.TextStyle.paragraph,
                                        max_length=300, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await db.execute(
            "INSERT INTO applications (guild_id,user_id,game_name,game_uid,role,status,created_at) VALUES (?,?,?,?,?,?,?)",
            (interaction.guild_id, interaction.user.id, str(self.nick), str(self.uid), str(self.role),
             "Pendente", datetime.now(timezone.utc).isoformat()))
        await db.commit()
        review_id = int(os.getenv("APPLICATION_CHANNEL_ID", "0"))
        channel = interaction.guild.get_channel(review_id) if review_id else None
        if isinstance(channel, discord.TextChannel):
            e = discord.Embed(title="Nova candidatura • Lunar O.R.G", color=PURPLE)
            e.add_field(name="Discord", value=interaction.user.mention, inline=True)
            e.add_field(name="Nick / ID", value=f"{self.nick}\n`{self.uid}`", inline=True)
            e.add_field(name="Função", value=str(self.role), inline=True)
            e.add_field(name="Idade", value=str(self.age), inline=True)
            e.add_field(name="Disponibilidade", value=str(self.availability) or "Não informado", inline=False)
            await channel.send(embed=e, view=ApplicationReviewView())
        await audit(interaction.guild, "Candidatura", interaction.user.mention, f"Candidatura enviada: {self.nick}")
        await interaction.response.send_message("✅ Candidatura enviada para análise da equipe!", ephemeral=True)


class ApplicationReviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Aprovar", style=discord.ButtonStyle.success, custom_id="lunar:app:approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
            return await interaction.response.send_message("Você não tem permissão para revisar candidaturas.", ephemeral=True)
        await interaction.response.send_message("Candidatura marcada como aprovada. Avise o candidato e atribua os cargos manualmente.", ephemeral=True)
        if interaction.message and interaction.message.embeds:
            e = interaction.message.embeds[0]
            e.color = GREEN
            e.add_field(name="Revisão", value=f"Aprovada por {interaction.user.mention}", inline=False)
            await interaction.message.edit(embed=e)
        await audit(interaction.guild, "Candidatura aprovada", interaction.user.mention)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, custom_id="lunar:app:reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
            return await interaction.response.send_message("Você não tem permissão para revisar candidaturas.", ephemeral=True)
        await interaction.response.send_message("Candidatura marcada como recusada.", ephemeral=True)
        if interaction.message and interaction.message.embeds:
            e = interaction.message.embeds[0]
            e.color = RED
            e.add_field(name="Revisão", value=f"Recusada por {interaction.user.mention}", inline=False)
            await interaction.message.edit(embed=e)
        await audit(interaction.guild, "Candidatura recusada", interaction.user.mention)


class EventModal(discord.ui.Modal, title="Criar evento • Lunar O.R.G"):
    title_text = discord.ui.TextInput(label="Nome do evento", max_length=80)
    kind = discord.ui.TextInput(label="Tipo", placeholder="Campeonato ou X-treino", max_length=30)
    description = discord.ui.TextInput(label="Detalhes / data / horário", style=discord.TextStyle.paragraph, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
            return await interaction.response.send_message("Somente a equipe pode criar eventos.", ephemeral=True)
        cur = await db.execute(
            "INSERT INTO events (guild_id,title,kind,description,created_by,created_at) VALUES (?,?,?,?,?,?)",
            (interaction.guild_id, str(self.title_text), str(self.kind), str(self.description),
             interaction.user.id, datetime.now(timezone.utc).isoformat()))
        await db.commit()
        event_id = cur.lastrowid
        channel_id = int(os.getenv("EVENT_CHANNEL_ID", "0"))
        channel = interaction.guild.get_channel(channel_id) if channel_id else None
        if isinstance(channel, discord.TextChannel):
            e = discord.Embed(title=f"🏆 {self.title_text}", description=str(self.description), color=PURPLE)
            e.add_field(name="Tipo", value=str(self.kind), inline=True)
            e.add_field(name="Código", value=f"#{event_id}", inline=True)
            e.set_footer(text="Clique em Confirmar presença para registrar sua participação.")
            await channel.send(embed=e, view=AttendanceView(event_id))
        await interaction.response.send_message(f"Evento criado (#{event_id}).", ephemeral=True)
        await audit(interaction.guild, "Evento criado", interaction.user.mention, str(self.title_text))


class AttendanceView(discord.ui.View):
    def __init__(self, event_id: int):
        super().__init__(timeout=None)
        self.event_id = event_id

    @discord.ui.button(label="✅ Confirmar presença", style=discord.ButtonStyle.success)
    async def attend(self, interaction: discord.Interaction, button: discord.ui.Button):
        await db.execute("INSERT OR REPLACE INTO attendance (event_id,user_id,status) VALUES (?,?,?)",
                         (self.event_id, interaction.user.id, "Confirmado"))
        await db.commit()
        await interaction.response.send_message("Presença confirmada! 🌙", ephemeral=True)

    @discord.ui.button(label="❌ Não vou", style=discord.ButtonStyle.secondary)
    async def absent(self, interaction: discord.Interaction, button: discord.ui.Button):
        await db.execute("INSERT OR REPLACE INTO attendance (event_id,user_id,status) VALUES (?,?,?)",
                         (self.event_id, interaction.user.id, "Ausente"))
        await db.commit()
        await interaction.response.send_message("Resposta registrada.", ephemeral=True)


class TeamModal(discord.ui.Modal, title="Cadastrar time • Lunar O.R.G"):
    name = discord.ui.TextInput(label="Nome do time", max_length=50)
    captain = discord.ui.TextInput(label="Capitão (menção ou nome)", max_length=80)
    roster = discord.ui.TextInput(label="Line-up (nick dos jogadores)", style=discord.TextStyle.paragraph, max_length=400)

    async def on_submit(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
            return await interaction.response.send_message("Somente a equipe pode cadastrar times.", ephemeral=True)
        await db.execute("INSERT INTO teams (guild_id,name,captain_id,roster,created_at) VALUES (?,?,?,?,?)",
                         (interaction.guild_id, str(self.name), interaction.user.id, str(self.roster),
                          datetime.now(timezone.utc).isoformat()))
        await db.commit()
        await interaction.response.send_message(f"Time **{self.name}** cadastrado!", ephemeral=True)
        await audit(interaction.guild, "Time cadastrado", interaction.user.mention, f"{self.name}\n{self.roster}")


class SanctionModal(discord.ui.Modal, title="Registrar advertência"):
    user_id = discord.ui.TextInput(label="ID Discord do jogador", max_length=24)
    kind = discord.ui.TextInput(label="Tipo", placeholder="Advertência / suspensão", max_length=30)
    reason = discord.ui.TextInput(label="Motivo", style=discord.TextStyle.paragraph, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
            return await interaction.response.send_message("Somente a equipe pode registrar punições.", ephemeral=True)
        try:
            uid = int(str(self.user_id))
        except ValueError:
            return await interaction.response.send_message("O ID precisa ser numérico.", ephemeral=True)
        await db.execute("INSERT INTO sanctions (guild_id,user_id,moderator_id,kind,reason,created_at) VALUES (?,?,?,?,?,?)",
                         (interaction.guild_id, uid, interaction.user.id, str(self.kind), str(self.reason),
                          datetime.now(timezone.utc).isoformat()))
        await db.commit()
        await interaction.response.send_message("Registro salvo no banco de dados.", ephemeral=True)
        await audit(interaction.guild, "Punição registrada", interaction.user.mention,
                    f"Jogador: <@{uid}>\nTipo: {self.kind}\nMotivo: {self.reason}")


class OrgPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 Recrutamento", style=discord.ButtonStyle.primary, custom_id="lunar:recruit", row=0)
    async def recruit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RecruitmentModal())

    @discord.ui.button(label="👥 Times / Line-ups", style=discord.ButtonStyle.secondary, custom_id="lunar:teams", row=0)
    async def teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        cur = await db.execute("SELECT name,captain_id,roster FROM teams WHERE guild_id=? ORDER BY id DESC LIMIT 10",
                               (interaction.guild_id,))
        rows = await cur.fetchall()
        e = discord.Embed(title="👥 Times e line-ups", color=PURPLE)
        if not rows:
            e.description = "Nenhum time cadastrado ainda."
        else:
            for name, captain, roster in rows:
                e.add_field(name=name, value=f"Capitão: <@{captain}>\nLine-up: {roster}", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="🏆 Campeonatos / X-treinos", style=discord.ButtonStyle.primary, custom_id="lunar:events", row=0)
    async def events(self, interaction: discord.Interaction, button: discord.ui.Button):
        cur = await db.execute("SELECT id,title,kind,description FROM events WHERE guild_id=? ORDER BY id DESC LIMIT 8",
                               (interaction.guild_id,))
        rows = await cur.fetchall()
        e = discord.Embed(title="🏆 Campeonatos e X-treinos", color=PURPLE)
        if not rows:
            e.description = "Nenhum evento publicado ainda."
        else:
            for eid, title, kind, desc in rows:
                e.add_field(name=f"#{eid} • {title} ({kind})", value=desc, inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="📊 Ranking", style=discord.ButtonStyle.secondary, custom_id="lunar:ranking", row=1)
    async def ranking(self, interaction: discord.Interaction, button: discord.ui.Button):
        cur = await db.execute("""SELECT user_id, COUNT(*) FROM attendance
                                  WHERE status='Confirmado' GROUP BY user_id
                                  ORDER BY COUNT(*) DESC LIMIT 10""")
        rows = await cur.fetchall()
        e = discord.Embed(title="📊 Ranking de presença nos treinos", color=PURPLE)
        e.description = "\n".join(f"**{i}.** <@{uid}> — **{count}** presença(s)" for i, (uid, count) in enumerate(rows, 1)) or "Ainda não há presenças registradas."
        await interaction.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="🗓️ Presença nos treinos", style=discord.ButtonStyle.success, custom_id="lunar:attendance", row=1)
    async def attendance(self, interaction: discord.Interaction, button: discord.ui.Button):
        cur = await db.execute("SELECT id,title,kind,description FROM events WHERE guild_id=? ORDER BY id DESC LIMIT 5",
                               (interaction.guild_id,))
        rows = await cur.fetchall()
        e = discord.Embed(title="🗓️ Próximos / últimos eventos", color=PURPLE)
        e.description = "\n".join(f"**#{r[0]} — {r[1]}** · {r[2]}\n{r[3]}" for r in rows) or "Nenhum treino cadastrado."
        await interaction.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="🛡️ Administração", style=discord.ButtonStyle.danger, custom_id="lunar:admin", row=1)
    async def admin(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
            return await interaction.response.send_message("Painel restrito à equipe autorizada.", ephemeral=True)
        await interaction.response.send_message("Escolha uma ação:", view=AdminPanel(), ephemeral=True)


class AdminPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="➕ Criar campeonato / X-treino", style=discord.ButtonStyle.primary)
    async def create_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EventModal())

    @discord.ui.button(label="👥 Cadastrar time", style=discord.ButtonStyle.secondary)
    async def create_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TeamModal())

    @discord.ui.button(label="⚠️ Registrar advertência", style=discord.ButtonStyle.danger)
    async def sanction(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SanctionModal())


@bot.event
async def on_ready():
    if db is None:
        await init_db()
    bot.add_view(OrgPanel())
    bot.add_view(ApplicationReviewView())
    if GUILD_ID:
        guild_obj = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild_obj)
        await bot.tree.sync(guild=guild_obj)
    else:
        await bot.tree.sync()
    log.info("Conectado como %s", bot.user)


@bot.event
async def on_member_join(member: discord.Member):
    await audit(member.guild, "Entrada", member.mention, f"{member} entrou no servidor.")


@bot.event
async def on_member_remove(member: discord.Member):
    await audit(member.guild, "Saída", str(member), f"{member} saiu do servidor.")


@bot.tree.command(name="painel-org", description="Publica o painel principal da Lunar O.R.G.")
async def panel_command(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
        return await interaction.response.send_message("Somente a equipe autorizada pode publicar o painel.", ephemeral=True)
    await interaction.channel.send(embed=main_embed(), view=OrgPanel())
    await interaction.response.send_message("Painel publicado!", ephemeral=True)


@bot.tree.command(name="painel-admin", description="Abre o painel administrativo da Lunar O.R.G.")
async def admin_command(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
        return await interaction.response.send_message("Acesso negado.", ephemeral=True)
    await interaction.response.send_message("Painel administrativo:", view=AdminPanel(), ephemeral=True)


@bot.tree.command(name="minhas-presencas", description="Mostra suas presenças confirmadas.")
async def my_attendance(interaction: discord.Interaction):
    cur = await db.execute("SELECT COUNT(*) FROM attendance WHERE user_id=? AND status='Confirmado'",
                           (interaction.user.id,))
    count = (await cur.fetchone())[0]
    await interaction.response.send_message(f"Você tem **{count}** presença(s) confirmada(s).", ephemeral=True)


@bot.tree.command(name="minhas-advertencias", description="Mostra suas advertências registradas.")
async def my_sanctions(interaction: discord.Interaction):
    cur = await db.execute("SELECT kind,reason,created_at FROM sanctions WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10",
                           (interaction.guild_id, interaction.user.id))
    rows = await cur.fetchall()
    e = discord.Embed(title="⚠️ Minhas advertências", color=PURPLE)
    e.description = "\n".join(f"**{kind}** — {reason} · {date[:10]}" for kind, reason, date in rows) or "Nenhuma advertência registrada."
    await interaction.response.send_message(embed=e, ephemeral=True)


async def main():
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
