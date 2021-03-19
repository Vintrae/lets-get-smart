#include <unistd.h>
#include <sys/types.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <stdlib.h>
#include <scsi/sg.h>
#include <scsi/scsi_ioctl.h>
#include <string.h>
#include <time.h>

#define ASCII_S 83
#define SG_DXFER_FROM_DEV -3
#define SG_IO 0x2285  // <scsi/sg.h>

typedef struct ata_command {
    unsigned char opcode;
    unsigned char protocol;
    unsigned char flags;
    unsigned char features;
    unsigned char sector_count;
    unsigned char lba_low;
    unsigned char lba_mid;
    unsigned char lba_high;
    unsigned char device;
    unsigned char command;
    unsigned char reserved;
    unsigned char control;
} ata_command;

typedef struct SgioHdr {
    int interface_id;
    int dxfer_direction;
    unsigned char cmd_len;
    unsigned char mx_sb_len;
    unsigned short iovec_count;
    unsigned int dxfer_len;
    void * dxferp;
    unsigned char * cmdp;
    unsigned char * sbp;
    unsigned int timeout;
    unsigned int flags;
    int pack_id;
    void * usr_ptr;
    unsigned char status;
    unsigned char masked_status;
    unsigned char msg_status;
    unsigned char sb_len_wr;
    unsigned short host_status;
    unsigned short driver_status;
    int resid;
    unsigned int duration;
    unsigned int info;
} SgioHdr;

void GetSmartsSgIo(char dev[]) {
    time_t start;
    int fd = 0;
    // Check if provided path is absolute. If not, append '/dev/' at the beginning of it.
    char path[20];
    if(strncmp(dev, "/", 1) != 0) {
        strcpy(path, "/dev/");
        strcat(path, dev);
    }
    else {
        strcpy(path, dev);
    }
    printf("Target: '%s'\n", path);

    // Build the Command Descriptor Block.
    ata_command ata_cmd = {
                   .opcode=0xa1,  // ATA PASS-THROUGH (12)
                   .protocol=0x0c,  // DMA
                   // flags field
                   // OFF_LINE = 0 (0 seconds offline)
                   // CK_COND = 0 (don't copy sense data in response)
                   // T_DIR = 1 (transfer from the ATA device)
                   // BYT_BLOK = 1 (length is in blocks, not bytes)
                   // T_LENGTH = 2 (transfer length in the SECTOR_COUNT field)
                   .flags=0x0e,
                   .features=0xd0,  // SMART READ DATA
                   .sector_count=1,
                   .lba_low=0, .lba_mid=0x4f, .lba_high=0xc2,
                   .device=0,
                   .command=0xb0,  // Read S.M.A.R.T Log
                   .reserved=0, .control=0};

    unsigned char sense[64];
    // Create return buffer and initialise to 0.
    unsigned char return_buffer[512];
    for(register int index = 0 ; index < 512; return_buffer[index++] = 0);

    // Create sg_io_hdr.
    SgioHdr sgio = {.interface_id=ASCII_S, .dxfer_direction=SG_DXFER_FROM_DEV,
                    .cmd_len=sizeof(ata_cmd),
                    .mx_sb_len=sizeof(sense), .iovec_count=0,
                    .dxfer_len=sizeof(return_buffer),
                    .dxferp=(void *)return_buffer,
                    .cmdp=&ata_cmd,
                    .sbp=(unsigned char *)sense, .timeout=20000,
                    .flags=0, .pack_id=0, .usr_ptr=NULL, .status=0, .masked_status=0,
                    .msg_status=0, .sb_len_wr=0, .host_status=0, .driver_status=0,
                    .resid=0, .duration=0, .info=0};

    // Open device in the specified path.
    if((fd = open(path, O_RDONLY)) < 0 ) {
        printf("Could not open device file\n");
        return;
    }

    start = time(NULL);
    // Call ioctl on fd.
    if(ioctl(fd, SG_IO, &sgio) < 0) {
        printf("IOCTL FAILED CALL\n");
        return;
    }
    printf("IOCTL call: %d sec.\n", time(NULL) - start);

    double raw;
    int id;
    printf("ID\t\tONLINE-OFFLINE\t\tRAW-VALUE\n");
    for(register int index = 2;index < 361 ; index = index+12 ) {    
        id = (int)return_buffer[index];
        if(id == 0) {
            continue;
        }
        printf("%d\t\t", id);

        if(return_buffer[index+1] & 0x00000002) {
            printf("ONLINE+OFFLINE\t\t");
        }
        else {
            printf("OFFLINE \t\t");
        }

        raw = 0;
        if(id == 194) {
            int temp = (int)return_buffer[index+5];
            int temp_min = (int)return_buffer[index+7];
            int temp_max = (int)return_buffer[index+9];
            printf("%d (Min %d/Max %d)", temp, temp_min, temp_max);
        }
        else {
            raw = (long long int)((return_buffer[index+5]) | 
                                  (return_buffer[index+6]<<8) | 
                                  (return_buffer[index+7]<<16) | 
                                  (return_buffer[index+8]<<24) | 
                                  ((long long int)return_buffer[index+9]<<32) | 
                                  ((long long int)return_buffer[index+10]<<40));
            printf("%lld\t\t\t",(long long int)raw);
        }
        printf("\n");
    }
}

int main(int argc, char *argv[]) {
    // Check an argument was provided.
    if(argc < 2){
        printf("Enter a device filename\n");
        return 1;
    }
    GetSmartsSgIo(argv[1]);
    return 0;
}
