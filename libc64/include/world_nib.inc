; world_nib.inc - lecture des jetons du monde codés en quartets (libc64/world,
; format : tools/mkworld.py). Écrit à la main, utilisé par world_core.s,
; world_render.s et world_render_col.s.
;
; Un segment commence sur un octet entier ; ses jetons (octets du codage
; littéraux/répétitions) sont codés en quartets, poids fort d'abord :
;   quartet 0-14 : jeton = world_nib_top[quartet] (les 15 jetons les plus
;                  fréquents) ;
;   quartet 15   : échappement, le jeton est dans les 2 quartets suivants.
; État : ptr1 = octet suivant à lire ; world_nib_half = 1 si le quartet bas
; de l'octet précédent (world_nib_pend) reste à lire. Mettre world_nib_half
; à 0 au début de chaque segment.

.import world_nib_top
.ifndef WORLD_NIB_STATE                 ; défini par world_core.s, qui porte l'état
.import world_nib_half, world_nib_pend, world_nib_tmp
.endif

; A = octet suivant (ptr1), ptr1 avancé ; X = 0.
.macro NIB_READ
        .local nocarry
        ldx #0
        lda (ptr1,x)
        inc ptr1
        bne nocarry
        inc ptr1+1
nocarry:
.endmacro

; A = octet suivant ((ptr1),y), Y avancé : plus rapide, quand Y est libre
; (segment de moins de 256 octets).
.macro NIB_READ_Y
        lda (ptr1),y
        iny
.endmacro

; A = jeton suivant. Modifie X ; préserve Y (NIB_TOKEN) ou s'en sert comme
; position dans le segment (NIB_TOKEN Y : Y = 0 au début du segment).
.macro NIB_TOKEN mode
        .local fromhalf, esc_hi, done
        lda world_nib_half
        bne fromhalf
        .ifblank mode
        NIB_READ
        .else
        NIB_READ_Y
        .endif
        tax
        and #$0F
        sta world_nib_pend
        txa
        lsr a
        lsr a
        lsr a
        lsr a
        inc world_nib_half      ; le quartet bas reste à lire
        cmp #15
        beq esc_hi
        tax
        lda world_nib_top,x
        jmp done
esc_hi: lda world_nib_pend      ; jeton = quartet bas << 4 | quartet haut de l'octet suivant
        asl a
        asl a
        asl a
        asl a
        sta world_nib_tmp
        .ifblank mode
        NIB_READ
        .else
        NIB_READ_Y
        .endif
        tax
        and #$0F
        sta world_nib_pend      ; son quartet bas reste à lire (world_nib_half = 1)
        txa
        lsr a
        lsr a
        lsr a
        lsr a
        ora world_nib_tmp
        jmp done
fromhalf:
        ldx #0
        stx world_nib_half
        ldx world_nib_pend
        cpx #15
        bne :+
        .ifblank mode           ; échappement en quartet bas : l'octet suivant entier
        NIB_READ
        .else
        NIB_READ_Y
        .endif
        jmp done
:       lda world_nib_top,x
done:
.endmacro
