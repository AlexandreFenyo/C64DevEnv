; panel_done() : retire les deux handlers du panneau (libc64/raster). Le
; mode du VIC-II reste celui qu'ils ont laissé.

        .export _panel_done
        .import panel_split1, panel_split2, _raster_unregister

        .segment "CODE"

.proc _panel_done
        lda #<panel_split1
        ldx #>panel_split1
        jsr _raster_unregister
        lda #<panel_split2
        ldx #>panel_split2
        jmp _raster_unregister
.endproc
