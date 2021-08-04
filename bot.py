#  This is just a cog with a command in it

from discord.ext import commands
import discord
import json
import aiohttp
from PIL import Image
from io import BytesIO
import numpy as np
import cv2
import potrace  # only works on linux (VPS uses linux)


def get_contours(pil_image, nudge):
    # Convert PIL Image into cv2 image
    image = np.asarray(pil_image)
    # Turn image to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Calculate lower and upper bounds (determines what are the edges)
    median = max(10, min(245, np.median(gray)))
    lower = int(max(0, (1 - nudge) * median))
    upper = int(min(255, (1 + nudge) * median))
    # Smooth it out
    filtered = cv2.bilateralFilter(gray, 5, 50, 50)
    # Find and return the edges
    edged = cv2.Canny(filtered, lower, upper, L2gradient=True)

    return edged[::-1]


def get_trace(data):
    # Turns the edges into a path that can be used to generate bezier curve equations
    for i in range(len(data)):
        data[i][data[i] > 1] = 1
    bmp = potrace.Bitmap(data)
    path = bmp.trace(2, potrace.TURNPOLICY_MINORITY, 1.0, 1, .5)
    return path


def get_latex(pil_image, nudge=0.33):
    # Generate equations from PIL Image and potrace'd path

    latex = []
    path = get_trace(get_contours(pil_image, nudge))

    for curve in path.curves:
        segments = curve.segments
        start = curve.start_point
        for segment in segments:
            x0, y0 = start
            if segment.is_corner:
                x1, y1 = segment.c
                x2, y2 = segment.end_point
                latex.append('((1-t)%f+t%f,(1-t)%f+t%f)' % (x0, x1, y0, y1))
                latex.append('((1-t)%f+t%f,(1-t)%f+t%f)' % (x1, x2, y1, y2))
            else:
                x1, y1 = segment.c1
                x2, y2 = segment.c2
                x3, y3 = segment.end_point
                latex.append('((1-t)((1-t)((1-t)%f+t%f)+t((1-t)%f+t%f))+t((1-t)((1-t)%f+t%f)+t((1-t)%f+t%f)),\
                (1-t)((1-t)((1-t)%f+t%f)+t((1-t)%f+t%f))+t((1-t)((1-t)%f+t%f)+t((1-t)%f+t%f)))' % \
                (x0, x1, x1, x2, x1, x2, x2, x3, y0, y1, y1, y2, y1, y2, y2, y3))
            start = segment.end_point
    return latex


class Desmos(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def render(self, ctx, color, dim, url, nudge):
        await ctx.send('Rendering...')
        # Get image data from url
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                imdata = await resp.read()

        # So we dont block the bot
        def executor():
            image = Image.open(BytesIO(imdata))
            r = image.size[0] / image.size[1]
            x = dim
            y = round(x / r)
            image = image.resize((x, y)).convert(mode='RGB')
            latex = get_latex(image, nudge)

            # Make a .txt file with equations joined with newlines
            txt = BytesIO()
            txt.write('\n'.join(latex).encode('utf8'))
            txt.seek(0)

            # Put equations and color into json file
            with open('./equations.json', 'r+') as f:
                data = json.load(f)
                data[str(ctx.author.id)] = {
                    'color': '#' + '%02x%02x%02x' % color.to_rgb(),
                    'latex': latex
                }
                f.truncate(0)
                f.seek(0)
                json.dump(data, f, indent=2)

            # Modify HTML file to send request to /ctx.author.id
            with open('./index.html') as f:
                content = f.read().replace('USER_ID', str(ctx.author.id))
                new = BytesIO()
                new.write(bytes(content, 'utf8'))
                new.seek(0)
                return new, txt

        buffer, txt = await self.bot.loop.run_in_executor(None, executor)
        files = [
            discord.File(fp=buffer, filename='render.html'),
            discord.File(fp=txt, filename='equations.txt')
        ]
        await ctx.send(files=files)

    @commands.group(invoke_without_command=True)
    async def desmos(self, ctx, color: discord.Color = None, dim: int = 500, nudge: float = 0.33):
        """Renders desmos equations from an image file."""
        if not color:
            color = discord.Color.from_rgb(0, 0, 0)
        a = ctx.message.attachments
        if not a:
            return await ctx.send('Please upload an image to render along with the command')
        im = a[0]
        await self.render(ctx, color, dim, im.url, nudge)

    @desmos.command()
    async def url(self, ctx, url, color: discord.Color = None, dim: int = 500, nudge: float = 0.33):
        """Renders desmos equations from an image URL."""
        if not color:
            color = discord.Color.from_rgb(0, 0, 0)
        await self.render(ctx, color, dim, url, nudge)


def setup(bot):
    bot.add_cog()
