/*
 * MMAL Video render example app
 *
 * Copyright © 2017 Raspberry Pi (Trading) Ltd.
 *
 * This file is subject to the terms and conditions of the GNU General Public
 * License.  See the file COPYING in the main directory of this archive
 * for more details.
 */

#include <stdio.h>
#include <stdlib.h>
#include <interface/mmal/mmal.h>
#include <interface/mmal/util/mmal_util.h>
#include <interface/mmal/util/mmal_connection.h>
#include <interface/mmal/util/mmal_util_params.h>
#include <cairo/cairo.h>
#include <sys/statvfs.h>
#include "utils.h"


#include <string.h>
#include <assert.h>
#include <time.h>

#include <getopt.h>             /* getopt_long() */

#include <fcntl.h>              /* low-level i/o */
#include <unistd.h>
#include <errno.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/time.h>
#include <sys/mman.h>
#include <sys/ioctl.h>

#include <linux/videodev2.h>


#define ENCODING    MMAL_ENCODING_RGB24
#define WIDTH  2048
#define HEIGHT 1152

#define BWIDTH  2048
#define BHEIGHT 1152
#define ALIGN16(x) (((x+0xf)>>4)<<4)

#define MAX_ENCODINGS_NUM 25
typedef struct {
   MMAL_PARAMETER_HEADER_T header;
   MMAL_FOURCC_T encodings[MAX_ENCODINGS_NUM];
} MMAL_SUPPORTED_ENCODINGS_T;


long millis(){
    struct timespec _t;
    clock_gettime(CLOCK_REALTIME, &_t);
    return _t.tv_sec*1000 + lround(_t.tv_nsec/1.0e6);
}


static void callback_vr_input(MMAL_PORT_T *port, MMAL_BUFFER_HEADER_T *buffer)
{
    mmal_buffer_header_release(buffer);
}

static int get_video_format(int fd, struct v4l2_format *fmt)
{
    int ret;
    fmt->type = 1;
    ret = ioctl(fd, VIDIOC_G_FMT, fmt);
	if (ret < 0)
	{
		printf("Unable to set format: %s (%d).\n", strerror(errno),
			  errno);
	}
    return ret;
}

static int query_control(int fd, unsigned int id, struct v4l2_queryctrl *query)
{
	int ret;

	memset(query, 0, sizeof(*query));
	query->id = id;

	ret = ioctl(fd, VIDIOC_QUERYCTRL, query);
	if (ret < 0 && errno != EINVAL)
		printf("unable to query control 0x%8.8x: %s (%d).\n",
			  id, strerror(errno), errno);

	return ret;
}

static int get_control(int fd, const struct v4l2_queryctrl *query, struct v4l2_ext_control *ctrl)
{
	struct v4l2_ext_controls ctrls;
	int ret;

	memset(&ctrls, 0, sizeof(ctrls));
	memset(ctrl, 0, sizeof(*ctrl));

	ctrls.ctrl_class = V4L2_CTRL_ID2CLASS(query->id);
	ctrls.count = 1;
	ctrls.controls = ctrl;

	ctrl->id = query->id;

	if (query->type == V4L2_CTRL_TYPE_STRING)
	{
		ctrl->string = malloc(query->maximum + 1);
		if (ctrl->string == NULL)
			return -ENOMEM;

		ctrl->size = query->maximum + 1;
	}

	ret = ioctl(fd, VIDIOC_G_EXT_CTRLS, &ctrls);
	if (ret != -1)
		return 0;

	if (query->type != V4L2_CTRL_TYPE_INTEGER64 &&
		query->type != V4L2_CTRL_TYPE_STRING &&
		(errno == EINVAL || errno == ENOTTY))
	{
		struct v4l2_control old;

		old.id = query->id;
		ret = ioctl(fd, VIDIOC_G_CTRL, &old);
		if (ret != -1)
		{
			ctrl->value = old.value;
			return 0;
		}
	}

	printf("unable to get control 0x%8.8x: %s (%d).\n",
		  query->id, strerror(errno), errno);
	return -1;
}


static int video_get_control(int fd, unsigned int id)
{
	struct v4l2_ext_control ctrl;
	struct v4l2_queryctrl query;
	int ret;

	ret = query_control(fd, id, &query);

	ret = get_control(fd, &query, &ctrl);
	return ctrl.value;
}

// static unsigned int get_shutter(int fd){
//     struct v4l2_format fmt = {0};
//     get_video_format(fd, &fmt);
//     double width = (double)fmt.fmt.pix.width;
//     unsigned long exposure = video_get_control(fd, 0x00980911);
//     double pxrate = 840000000.0;
//     double hz_blank = 10712.0;
//     float ex_ms = ((width+hz_blank) / pxrate) * exposure;

//     return (unsigned int )(1 / ex_ms);
// }

static unsigned int get_shutter(int fd){
    struct v4l2_format fmt = {0};
    get_video_format(fd, &fmt);
    double width = (double)fmt.fmt.pix.width;
    unsigned long exposure = video_get_control(fd, 0x00980911);
    double pxrate = 840000000.0;
    double hz_blank = 10712.0;
    float ex_ms = ((width+hz_blank) / pxrate) * exposure;
    double v_blank = (double)video_get_control(fd, 0x009e0901);
    double h = (double)fmt.fmt.pix.height;
    double w = (double)fmt.fmt.pix.width;
    
    float fps_1 = pxrate / ((w+hz_blank) * (h+v_blank));

    return (unsigned int )(1+(360 * pxrate / ((w+hz_blank) * (h+v_blank)) / (1/ex_ms)));
}

static unsigned int gain_to_iso(int gain_code){
    return (unsigned int) (1024.0 / (1024.0 - (double)gain_code) * 100.0);
}

static unsigned int get_fps(int fd){
    struct v4l2_format fmt = {0};
    get_video_format(fd, &fmt);
    double v_blank = (double)video_get_control(fd, 0x009e0901);
    double h = (double)fmt.fmt.pix.height;
    double w = (double)fmt.fmt.pix.width;
    double pxrate = 840000000.0;
    double hz_blank = 10712.0;

    return (unsigned int)pxrate / ((w+hz_blank) * (h+v_blank));
}

static float get_cpu_temp(){
    float systemp, millideg;
    FILE *thermal;
    int n;

    thermal = fopen("/sys/class/thermal/thermal_zone0/temp","r");
    n = fscanf(thermal,"%f",&millideg);
    fclose(thermal);
    systemp = millideg / 1000;

    return systemp;
}

struct cpu_util{
    long int sum;
    long int idle;
    long int lastSum;
    long int lastIdle;
    long double idleFraction;
};

static long double get_cpu_util(struct cpu_util *util){

        char str[100];
        const char d[2] = " ";
        char* token;
        int i = 0,times,lag;

        FILE* fp = fopen("/proc/stat","r");
	    i = 0;
        fgets(str,100,fp);
        fclose(fp);
        token = strtok(str,d);
                util->sum = 0;
        while(token!=NULL){
            token = strtok(NULL,d);
            if(token!=NULL){
                util->sum += atoi(token);

            if(i==3)
                util->idle = atoi(token);

            i++;
                }
            }
            util->idleFraction = 100 - (util->idle-util->lastIdle)*100.0/(util->sum-util->lastSum);

            util->lastIdle = util->idle;
            util->lastSum = util->sum;
}


void box_text (cairo_t *cr, const char *utf8, double x, double y){
    cairo_save (cr);

	cairo_surface_t *sr = cairo_get_target(cr);
    cairo_select_font_face (cr, "sans-serif", CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD);

    /** write text */
	cairo_move_to (cr, x, y);
	cairo_set_source_rgb (cr, 0.93, 0.93, 0.93);
    cairo_show_text (cr, utf8);
    
	/** draw outline */
    // cairo_move_to (cr, x, y);
    // cairo_text_path (cr, utf8);
    // cairo_set_source_rgb (cr, 0, 0, 0);
    // cairo_set_line_width (cr, 1);
    // cairo_stroke (cr);

    cairo_restore (cr);
}

int main()
{   
    cairo_surface_t *surface;
    cairo_t *cr;
    cairo_text_extents_t extents;
    cairo_font_extents_t font_extents;
    cairo_text_extents_t text_extents;
    double dx, dy;
    int stride;
    {
        cairo_format_t FORTMAT = CAIRO_FORMAT_ARGB32;
        
        stride = cairo_format_stride_for_width (FORTMAT, ALIGN16(BWIDTH));
        unsigned char *data = (unsigned char*)malloc(stride * ALIGN16(BHEIGHT));
        surface = cairo_image_surface_create_for_data(data, FORTMAT, ALIGN16(BWIDTH), ALIGN16(BHEIGHT), stride);
        if(!surface)
            printf ("invalid pointer\n");
        
        

        cr = cairo_create (surface);

        cairo_set_source_rgb (cr, 0., 0., 0.);
        // cairo_select_font_face (cr, "sans-serif", CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD);
        cairo_set_font_size (cr,36.0);
                
        fprintf(stderr, "stride: %d\n",stride);
        fprintf(stderr, "surfgace width: %d\n", cairo_image_surface_get_width(surface));
        fprintf(stderr, "surfgace height: %d\n", cairo_image_surface_get_height(surface));
        fprintf(stderr, "size: %d\n", (stride * BHEIGHT));

    }


    MMAL_COMPONENT_T *render = NULL;
    MMAL_PORT_T *input;
    MMAL_POOL_T *pool;
    MMAL_BUFFER_HEADER_T *buffer;
    int i;

    mmal_component_create("vc.ril.video_render", &render);
    input = render->input[0];

    input->format->encoding = MMAL_ENCODING_RGBA;
    input->format->es->video.width  = VCOS_ALIGN_UP(WIDTH,  32);
    input->format->es->video.height = VCOS_ALIGN_UP(HEIGHT, 16);
    input->format->es->video.crop.x = 0;
    input->format->es->video.crop.y = 0;
    input->format->es->video.crop.width  = WIDTH;
    input->format->es->video.crop.height = HEIGHT;
    mmal_port_format_commit(input);

    mmal_component_enable(render);

    mmal_port_parameter_set_boolean(input, MMAL_PARAMETER_ZERO_COPY, MMAL_TRUE);

    input->buffer_size = input->buffer_size_recommended;
    //input->buffer_size = (stride * HEIGHT);
    input->buffer_num = input->buffer_num_recommended;
    printf("buffer size: %d\n", input->buffer_size);

    if (input->buffer_num < 2)
        input->buffer_num = 2;
    pool = mmal_port_pool_create(input, input->buffer_num, input->buffer_size);

    if (!pool) {
        printf("Oops, ,pool alloc failed\n");
        return -1;
    }

    {
        MMAL_DISPLAYREGION_T param;
        param.hdr.id = MMAL_PARAMETER_DISPLAYREGION;
        param.hdr.size = sizeof(MMAL_DISPLAYREGION_T);

        param.set = MMAL_DISPLAY_SET_LAYER;
        param.layer = 127;    //On top of most things

        param.set |= MMAL_DISPLAY_SET_ALPHA;
        param.alpha = 255;    //0 = transparent, 255 = opaque

        param.set |= (MMAL_DISPLAY_SET_DEST_RECT | MMAL_DISPLAY_SET_FULLSCREEN);
        param.fullscreen = 1;
        param.dest_rect.x = 0;
        param.dest_rect.y = 0;
        param.dest_rect.width = WIDTH;
        param.dest_rect.height = HEIGHT;
        mmal_port_parameter_set(input, &param.hdr);
    }

    mmal_port_enable(input, callback_vr_input);

    struct v4l2_control control;
    struct v4l2_queryctrl queryctrl;

    int fd = open("/dev/video0", O_RDWR | O_NONBLOCK);
    if (fd == -1) {
        return -1;
    }

    struct cpu_util util = {0};

    unsigned int iso;
    unsigned int shutter;
    unsigned int fps;
    unsigned int resolution;
    float cpu_temp;

    char snum[32];
    char param_iso[32];
    char param_shutter[32];
    char param_fps[32];
    char param_resolution[32];
    char param_cpu_temp[32];
    char param_cpu_util[32];
    int bsize = (stride * BHEIGHT);


    double fsize, fblocks, ffree;
    struct statvfs stat;
    struct v4l2_format fmt = {0};

    const unsigned long eventInterval = 1000;
    unsigned long previousTime = 0;

    int update = 0;
    

    while (1) {
        /* Updates frequently */
        unsigned long currentTime = millis();

        if (statvfs("/media/RAW", &stat) != 0) {
            fsize = 0;
            ffree = 0;
        } else {
            fsize = ((double)stat.f_frsize) / (double)(1024);
            fblocks = ((double)stat.f_blocks) / (double)(1024);
            ffree = ((double)stat.f_bfree) / (double)(1024);
        }

        int iso_n = gain_to_iso(video_get_control(fd, 0x009e0903));
        if(iso_n != iso){
            iso = iso_n;
            update = 1;
        }

        int shutter_n = get_shutter(fd);
        if(shutter_n != shutter){
            shutter = shutter_n;
            update = 1;
        }

        int fps_n = get_fps(fd);
        if(fps_n != fps){
            fps = fps_n;
            update = 1;
        }

        float cpu_temp = get_cpu_temp();
        get_video_format(fd, &fmt);

        /* This is the event */
        if (currentTime - previousTime >= eventInterval || update) {

            get_cpu_util(&util);

            sprintf(snum, "%0.1f / %0.1f GB", (fsize * ffree)/1000, (fsize * fblocks)/1000);
            sprintf(param_iso, "%d", iso);
            sprintf(param_shutter, "%d°", shutter);
            sprintf(param_fps, "%d", fps);
            sprintf(param_resolution, "%dx%d", fmt.fmt.pix.width, fmt.fmt.pix.height);

            // sprintf(snum, "%0.1f / %0.1f GB", (fsize * ffree)/1000, (fsize * fblocks)/1000);
            // sprintf(param_iso, "%d", iso);
            // sprintf(param_shutter, "1/%d", shutter);
            // sprintf(param_fps, "%d", fps);
            // sprintf(param_resolution, "%dx%d", fmt.fmt.pix.width, fmt.fmt.pix.height);



            cairo_set_source_rgba (cr, 0, 0, 0, 0);
            cairo_set_operator (cr, CAIRO_OPERATOR_SOURCE);
            cairo_paint (cr);
            cairo_set_font_size (cr,36.0);

            box_text (cr, snum, 50, 1100);

            // box_text (cr, param_iso, 75, 100);
            // box_text (cr, param_shutter, 325, 100);
            // box_text (cr, param_fps, 725, 100);
            // box_text (cr, param_resolution, 1000, 100);

            label_text(cr, "ISO: ", param_iso, 75, 52);
            label_text(cr, "SHUTTER: ", param_shutter, 325, 52);
            label_text(cr, "FPS: ", param_fps, 725, 52);
            label_text(cr, "RES: ", param_resolution, 1000, 52);
            cpu_temp_text(cr, "%0.2f°C", "T: ", cpu_temp, 1450, 52);
            cpu_util_text(cr, "%0.2f%%", "CPU: ", util.idleFraction, 1750, 52);

            sized_box_text(cr, "CINEPI V1.0.0", 24.0, 1860, 1100);

            buffer = mmal_queue_wait(pool->queue);

            memcpy(buffer->data, cairo_image_surface_get_data(surface), bsize);
            buffer->length = buffer->alloc_size;
            mmal_port_send_buffer(input, buffer);

            
            cairo_surface_flush(surface);
            

            previousTime = currentTime;
            update = 0;
        }   

        usleep(10000);     
    }

    

    mmal_port_disable(input);
    mmal_component_destroy(render);

    return 0;
}