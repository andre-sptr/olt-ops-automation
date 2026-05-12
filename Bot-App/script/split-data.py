def split_text_file(input_file, max_size_mb=8):
    max_bytes = max_size_mb * 1024 * 1024
    file_count = 1
    current_size = 0
    current_file = None
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            if current_file is None:
                current_file = open(f"chat_bersih_part{file_count}.txt", 'w', encoding='utf-8')
            
            line_bytes = len(line.encode('utf-8'))
            if current_size + line_bytes > max_bytes:
                current_file.close()
                file_count += 1
                current_file = open(f"chat_bersih_part{file_count}.txt", 'w', encoding='utf-8')
                current_size = 0
            
            current_file.write(line)
            current_size += line_bytes
            
    if current_file:
        current_file.close()
    print(f"Selesai! File berhasil dipecah menjadi {file_count} bagian.")

split_text_file('chat_bersih.txt')