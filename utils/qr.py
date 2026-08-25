import io
import qrcode

def generate_shop_qr(bot_username: str, shop_id: int) -> io.BytesIO:
    deep_link = f"https://t.me/{bot_username}?start=shop_{shop_id}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(deep_link)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    bio = io.BytesIO()
    bio.name = f"shop_{shop_id}_qr.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio
