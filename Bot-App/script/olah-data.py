import re

def bersihkan_chat_tele(file_input, file_output):
    """
    Fungsi ini membaca file riwayat chat telegram, 
    menghapus blok tiket yang berulang, dan menyimpan versi terbarunya.
    """
    print("Memulai proses pembersihan data... ⏳")
    
    with open(file_input, 'r', encoding='utf-8') as f:
        konten = f.read()

    blok_tiket = konten.split('————————————————')

    tiket_terupdate = {}
    pola_inc = re.compile(r'INC[-\d]+')

    for blok in blok_tiket:
        blok_bersih = blok.strip()
        
        if not blok_bersih:
            continue
        
        pencarian = pola_inc.search(blok_bersih)
        
        if pencarian:
            id_tiket = pencarian.group()
            
            tiket_terupdate[id_tiket] = blok_bersih
        else:
            tiket_terupdate[blok_bersih] = blok_bersih

    with open(file_output, 'w', encoding='utf-8') as f:
        for isi_blok in tiket_terupdate.values():
            f.write(isi_blok + '\n')
            f.write('————————————————\n')

    print("Selesai! 🎉")
    print(f"Data berhasil dibersihkan dan disimpan di file: '{file_output}'")
    print(f"Total tiket unik yang berhasil disaring: {len(tiket_terupdate)}")

nama_file_input = 'chat_bersih.txt'
nama_file_output = 'chat_final_tanpa_duplikat.txt'

bersihkan_chat_tele(nama_file_input, nama_file_output)