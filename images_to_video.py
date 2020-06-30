#!/usr/bin/python3
import os, sys, math, time, re, json
import imageio, imageio_ffmpeg, cv2, exifread
import numpy as np

# Need some pylibs:
# sudo -H pip install exifread imageio imageio-ffmpeg opencv-python numpy

##########
# Params #
##########

# Default Params #

input_path = "."
input_filename = "IMG_\d+_.+.jpg"
output_path = '.'
output_filename = 'output'
output_format = 'mp4'

# CLI Params #

if len(sys.argv) == 1 or sys.argv[1] == '-h' or sys.argv[1] == '--help':
    print('''
Convert images to video
-------
Usage: {} <input_path> [output_filename] [filter_regex]
Params:
    input_path       Input file path
    output_filename  Output file name: default: `{}/{}.{}`
    filter_regex     Input file name filter regex, default: `{}`
'''.format(__file__, input_filename, output_path, output_filename, output_format))
    exit()
else:
    if len(sys.argv) >= 2:
        input_path = sys.argv[1]
        input_path = input_path.replace('\\', '/')
        if input_path[-1] == '/':
            input_path = input_path[:-1]
    if len(sys.argv) >= 3:
        output_path = os.path.dirname(sys.argv[2])
        output_path = output_path if output_path != '' else '.'
        output_filename = os.path.splitext(os.path.basename(sys.argv[2]))[0]
        output_format = os.path.splitext(os.path.basename(sys.argv[2]))[1][1:]
        output_format = output_format if output_format != '' else 'mp4'
    if len(sys.argv) >= 4:
        input_filename = sys.argv[3]
    print('''
Input params:
-------
input  = `{}/{}`
output = `{}/{}.{}`
'''.format(input_path, input_filename, output_path, output_filename, output_format))

###########
# Prepare #
###########

# Prepare Input #

files = os.listdir(input_path) # 得到文件夹下的所有文件名称

# 按文件名排序
files.sort()
# 按时间排序
#sorted(files, key=lambda x: os.path.getmtime(os.path.join(input_path, x)))

matcher = re.compile(input_filename) # 过滤文件名
files = list(filter(lambda file: matcher.match(file), files))

if len(files) <= 0:
    print('[ERROR]', "Can't find any input files: {}/{}".format(input_path, input_filename))
    exit()

# Prepare Output #

target = output_path + '/' + output_filename

if not os.path.exists(output_path): # 判断路径是否存在
    os.makedirs(output_path)
    print('[INFO]', 'Create new directory:', output_path)

if os.path.exists(target + '.' + output_format): # 判断目标是否存在
    print('[INFO]', 'Target file:', target + '.' + output_format)
    i = input('[WARN] Target file exists, overwrite? [Y/n]')
    if not (i == 'y' or i == 'Y' or i == 'yes'):
        print('Cancelled')
        exit()

log_writer = open(target + '.log', 'w')
error_writer = None

#########
# Video #
#########

video_writer = imageio.get_writer(target + '_tmp.' + output_format, # 打开目标文件
    format='FFMPEG',
    fps=1,
    codec='libx264',
    output_params=[
        '-loop', '1',
        '-c:v', 'libx264', 
        '-x264-params', 'keyint=1:scenecut=0']
    )
video_size = None
#video_size = (height, width)

prev_time = time.time()
used_time = 0

def is_same(img):
    global video_size
    size = np.shape(img)
    if video_size is None:
        video_size = size
        print('[INFO]', 'Set video size:', get_size(img))
    return video_size[0] == size[0] and video_size[1] == size[1]

def get_size(img):
    if img is None:
        return '0x0';
    else:
        size = np.shape(img)
        return str(size[1]) + 'x' + str(size[0])

def show_status(status, file, img=None):
    if frame > 0:
        global prev_time, used_time
        now_time = time.time()
        used_time = used_time + (now_time - prev_time)
        prev_time = now_time
        left_time = int((used_time / frame) * (all_frame - frame))
    else:
        left_time = 0
    
    log = '{0}| {1} {2} {3}/{4} {5}'.format(status, file, get_size(img), str(frame), str(all_frame), format_time(left_time))
    print(log)

    log_writer.write(log + '\n')
    if status == 'X':
        global error_writer
        if error_writer is None:
            error_writer = open(target + '.error.log', 'w')
        error_writer.write(log + '\n')

def resize_img(img):
    background = [0, 0, 0]
    size = np.shape(img)
    if video_size[0]/video_size[1] < size[0]/size[1]:
        width = round(video_size[0] * size[1]/size[0])
        height = video_size[0]
        img = cv2.resize(img, dsize=(width, height), interpolation=cv2.INTER_NEAREST)
        border = (video_size[1] - width) / 2;
        img = cv2.copyMakeBorder(img, 0, 0, math.ceil(border), math.floor(border), cv2.BORDER_CONSTANT, value=background)
    else:
        width = video_size[1]
        height = round(video_size[1] * size[0]/size[1])
        img = cv2.resize(img, dsize=(width, height), interpolation=cv2.INTER_NEAREST)
        border = (video_size[0] - height) / 2;
        img = cv2.copyMakeBorder(img, math.ceil(border), math.floor(border), 0, 0, cv2.BORDER_CONSTANT, value=background)
    return img

def add_img_to_video(file):
    try:
        img = imageio.imread(file)
    except Exception as e:
        show_status('X', file)
        raise e
        return

    if is_same(img):
        show_status(' ', file, img)
    else:
        t_img = np.transpose(img, (1, 0, 2))
        if is_same(t_img):
            show_status('R', file, img)
            img = t_img
        else:
            show_status('C', file, img)
            img = resize_img(img)

    video_writer.append_data(img)

#############
# EXIF Data #
#############

subtitle_writer = None
less_writer = open(target + '.srt', 'w')
more_writer = open(target + '.more.srt', 'w')
json_writer = open(target + '.json.srt', 'w')

def add_line(line):
    subtitle_writer.write(str(line) + '\n')

# output: $TARGET.str
def add_less_text_to_subtitle(tags, file):
    if 'Image DateTime' in tags:
        add_line(tags['Image DateTime'])

# output: $TARGET.more.str
def add_more_text_to_subtitle(tags, file):
    for tag in tags:
        add_line(tag + ': ' + str(tags[tag]))

# output: $TARGET.json.str
def add_json_text_to_subtitle(tags, file):
    data = list()
    for tag in tags:
        tag_data = dict()
        tag_data['name'] = tag
        tag_data['tag'] = tags[tag].tag
        values = tags[tag].values
        if type(values) is str:
            tag_data['values'] = values
            tag_data['converted'] = False
        else:
            try:
                tag_data['values'] = json.loads(str(values))
                tag_data['converted'] = False
            except:
                tag_data['values'] = str(values)
                tag_data['converted'] = True
        data.append(tag_data)
    add_line(json.dumps(data))

def add_exif_to_subtitle(file):
    global subtitle_writer
    now_time = format_time(frame)

    f = open(file,'rb')
    tags = exifread.process_file(f, details=False)
    f.close()

    subtitle_writer = less_writer
    add_line(str(frame))
    add_line('{0},{1:0>3d} --> {0},{2:0>3d}'.format(now_time, 000, 999))
    add_less_text_to_subtitle(tags, file)
    add_line('')

    subtitle_writer = more_writer
    add_line(str(frame))
    add_line('{0},{1:0>3d} --> {0},{2:0>3d}'.format(now_time, 000, 999))
    add_more_text_to_subtitle(tags, file)
    add_line('')

    subtitle_writer = json_writer
    add_line(str(frame))
    add_line('{0},{1:0>3d} --> {0},{2:0>3d}'.format(now_time, 000, 999))
    add_json_text_to_subtitle(tags, file)
    add_line('')

#########
# Utils #
#########

def format_time(time):
    return '{:0>2d}:{:0>2d}:{:0>2d}'.format(int(time/3600), int((time%3600)/60), time%60)

#############
# Main Loop #
#############

def add_img(file):
    add_img_to_video(file)
    add_exif_to_subtitle(file)

frame = 0
all_frame = len(files)

for file in files: # 遍历图片
    try:
        add_img(input_path + '/' + file)
        frame = frame + 1
    except Exception as e:
        print('ERROR', 'An error occured, skip frame %d.' % frame)
        all_frame = all_frame - 1

add_img(input_path + '/' + files[all_frame - 1])

video_writer.close()
less_writer.close()
more_writer.close()
json_writer.close()
log_writer.close()
if not error_writer is None:
    error_writer.close()

#########
# Merge #
#########

res = os.system('''{ffmpeg} \
    -i "{0}_tmp.{1}" \
    -i "{0}.srt" \
    -i "{0}.more.srt" \
    -i "{0}.json.srt" \
    -map 0:v \
    -map 1 \
    -map 2 \
    -map 3 \
    -metadata:s:s:0 handler_name='DateTime' \
    -metadata:s:s:1 handler_name='EXIF' \
    -metadata:s:s:2 handler_name='JSON' \
    -metadata:s:s:0 handler='DateTime' \
    -metadata:s:s:1 handler='EXIF' \
    -metadata:s:s:2 handler='JSON' \
    -y -flags global_header \
    -c:v copy \
    -c:s mov_text \
    "{0}.{1}"
    '''.format(target, output_format, ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()))

if res == 0:
    os.remove(target + '_tmp.mp4')
    os.remove(target + '.srt')
    os.remove(target + '.more.srt')
    os.remove(target + '.json.srt')
else:
    print('[ERROR]', 'An error occured.')

