; Généré par tools/mktileset.py depuis libc64/tileset/tileset.txt : ne pas modifier.
;
; Motifs des codes $40-$FB (8 octets par code, ligne 0 en haut ;
; codes non définis : à zéro) et Color RAM par défaut de chaque code.

        .export _tileset_glyphs, _tileset_colors

        .segment "RODATA"

_tileset_glyphs:
        .byte $CC,$CC,$33,$33,$CC,$CC,$33,$33   ; $40 HERBE P01
        .byte $55,$55,$55,$69,$69,$55,$55,$55   ; $41 ROUTE_H P02
        .byte $55,$55,$55,$55,$55,$55,$55,$55   ; $42 ROUTE_V P02
        .byte $3C,$FF,$FF,$AA,$AA,$FF,$FF,$3C   ; $43 STOP P02
        .byte $14,$14,$14,$14,$14,$14,$14,$00   ; $44 POTEAU P02
        .byte $95,$95,$95,$95,$95,$95,$95,$95   ; $45 ROUTE_VG P02
        .byte $56,$56,$56,$56,$56,$56,$56,$56   ; $46 ROUTE_VD P02
        .byte $AA,$55,$55,$55,$55,$55,$55,$55   ; $47 ROUTE_HH P02
        .byte $55,$55,$55,$55,$55,$55,$55,$AA   ; $48 ROUTE_HB P02
        .byte $55,$55,$55,$55,$55,$55,$55,$AA   ; $49 ROUTE_TIRET_HAUT P02
        .byte $AA,$55,$55,$55,$55,$55,$55,$55   ; $4A ROUTE_TIRET_BAS P02
        .byte $56,$56,$56,$56,$56,$56,$56,$56   ; $4B TIRET_GAUCHE P02
        .byte $95,$95,$95,$95,$95,$95,$95,$95   ; $4C TIRET_DROITE P02
        .byte $00,$00,$00,$00,$00,$00,$00,$00   ; $4D VIDE P01
        .byte $FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF   ; $4E PLEIN P01
        .byte $00,$01,$03,$07,$0F,$1F,$3F,$7F   ; $4F TOIT_PENTE_G P03
        .byte $00,$80,$C0,$E0,$F0,$F8,$FC,$FE   ; $50 TOIT_PENTE_D P03
        .byte $FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF   ; $51 TOIT_PLEIN P03
        .byte $55,$55,$55,$55,$55,$55,$55,$55   ; $52 MUR_BETON P02
        .byte $55,$55,$69,$6D,$6D,$69,$55,$55   ; $53 FENETRE_CYAN P04
        .byte $55,$55,$55,$69,$7D,$7D,$7D,$7D   ; $54 PORTE_NOIRE P05
        .byte $00,$00,$20,$10,$10,$10,$10,$10   ; $55 CHEMINEE P02
        .byte $55,$55,$69,$69,$69,$69,$55,$55   ; $56 FENETRE_BLANCHE P05
        .byte $AA,$AA,$55,$55,$55,$55,$FF,$55   ; $57 TOIT_ETUDIE P05
        .byte $10,$10,$10,$10,$10,$10,$10,$10   ; $58 ANTENNE_SIMPLE P05
        .byte $10,$54,$10,$55,$10,$55,$10,$10   ; $59 ANTENNE_RATEAU P05
        .byte $28,$14,$14,$28,$14,$14,$28,$14   ; $5A FEU_HAUT_ETEINT P06
        .byte $28,$3C,$3C,$28,$14,$14,$28,$14   ; $5B FEU_HAUT_ROUGE P02
        .byte $28,$14,$14,$28,$3C,$3C,$28,$14   ; $5C FEU_HAUT_ORANGE P07
        .byte $28,$14,$14,$28,$14,$14,$28,$3C   ; $5D FEU_HAUT_VERT P08
        .byte $14,$28,$04,$04,$04,$04,$04,$00   ; $5E FEU_BAS_ETEINT P06
        .byte $3C,$28,$04,$04,$04,$04,$04,$00   ; $5F FEU_BAS_VERT P08
        .byte $FF,$EF,$FF,$FF,$FF,$FE,$FF,$FF   ; $60 EAU P04
        .byte $00,$00,$00,$00,$AA,$FF,$FF,$FF   ; $61 PISC_BORD_H P04
        .byte $FF,$FF,$FF,$AA,$00,$00,$00,$00   ; $62 PISC_BORD_B P04
        .byte $2F,$2F,$2F,$2F,$2F,$2F,$2F,$2F   ; $63 PISC_BORD_G P04
        .byte $F8,$F8,$F8,$F8,$F8,$F8,$F8,$F8   ; $64 PISC_BORD_D P04
        .byte $00,$00,$00,$00,$2A,$2F,$2F,$2F   ; $65 PISC_COIN_NO P04
        .byte $00,$00,$00,$00,$A8,$F8,$F8,$F8   ; $66 PISC_COIN_NE P04
        .byte $2F,$2F,$2F,$2A,$00,$00,$00,$00   ; $67 PISC_COIN_SO P04
        .byte $F8,$F8,$F8,$A8,$00,$00,$00,$00   ; $68 PISC_COIN_SE P04
        .byte $2F,$2F,$2F,$2F,$AF,$FF,$FF,$FF   ; $69 PISC_CONC_NO P04
        .byte $F8,$F8,$F8,$F8,$FA,$FF,$FF,$FF   ; $6A PISC_CONC_NE P04
        .byte $FF,$FF,$FF,$AF,$2F,$2F,$2F,$2F   ; $6B PISC_CONC_SO P04
        .byte $FF,$FF,$FF,$FA,$F8,$F8,$F8,$F8   ; $6C PISC_CONC_SE P04
        .byte $AA,$AA,$FF,$FF,$FF,$FF,$FF,$FF   ; $6D LAC_BORD_H P04
        .byte $FF,$FF,$FF,$FF,$FF,$FF,$AA,$AA   ; $6E LAC_BORD_B P04
        .byte $BF,$BF,$BF,$BF,$BF,$BF,$BF,$BF   ; $6F LAC_BORD_G P04
        .byte $FE,$FE,$FE,$FE,$FE,$FE,$FE,$FE   ; $70 LAC_BORD_D P04
        .byte $0A,$0A,$2B,$2F,$BF,$BF,$BF,$BF   ; $71 LAC_NO P04
        .byte $A0,$A0,$E8,$F8,$FE,$FE,$FE,$FE   ; $72 LAC_NE P04
        .byte $BF,$BF,$BF,$BF,$2F,$2B,$0A,$0A   ; $73 LAC_SO P04
        .byte $FE,$FE,$FE,$FE,$F8,$E8,$A0,$A0   ; $74 LAC_SE P04
        .byte $BF,$BF,$FF,$FF,$FF,$FF,$FF,$FF   ; $75 LAC_CONC_NO P04
        .byte $FE,$FE,$FF,$FF,$FF,$FF,$FF,$FF   ; $76 LAC_CONC_NE P04
        .byte $FF,$FF,$FF,$FF,$FF,$FF,$BF,$BF   ; $77 LAC_CONC_SO P04
        .byte $FF,$FF,$FF,$FF,$FF,$FF,$FE,$FE   ; $78 LAC_CONC_SE P04
        .byte $3C,$FF,$EF,$FF,$3C,$04,$04,$00   ; $79 ARBRE_ROND P07
        .byte $0C,$3F,$FF,$3B,$3F,$0C,$04,$00   ; $7A ARBRE_CONIQUE P07
        .byte $3C,$FF,$FF,$EB,$FF,$3C,$14,$00   ; $7B ARBRE_TOUFFU P07
        .byte $CC,$CC,$30,$30,$C0,$C0,$00,$00   ; $7C DAMIER_NO P01
        .byte $CC,$CC,$0C,$0C,$0C,$0C,$03,$03   ; $7D DAMIER_NE P01
        .byte $C0,$C0,$30,$30,$CC,$CC,$33,$33   ; $7E DAMIER_SO P01
        .byte $00,$00,$03,$03,$0C,$0C,$33,$33   ; $7F DAMIER_SE P01
        .byte $55,$6A,$6F,$6F,$6F,$6F,$6F,$6F   ; $80 GARAGE_HG P05
        .byte $55,$A9,$F9,$F9,$F9,$F9,$F9,$F9   ; $81 GARAGE_HD P05
        .byte $6F,$6F,$6F,$6F,$6F,$6F,$6F,$6F   ; $82 GARAGE_BG P05
        .byte $F9,$F9,$F9,$F9,$F9,$F9,$F9,$F9   ; $83 GARAGE_BD P05
        .byte $55,$AA,$FF,$FF,$FF,$FF,$FF,$FF   ; $84 GARAGE_HM P05
        .byte $FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF   ; $85 GARAGE_BM P05
        .byte $FF,$FF,$FF,$FE,$FE,$FE,$AA,$AA   ; $86 CROIX_HG P02
        .byte $FF,$FF,$FF,$BF,$BF,$BF,$AA,$AA   ; $87 CROIX_HD P02
        .byte $AA,$AA,$FE,$FE,$FE,$FF,$FF,$FF   ; $88 CROIX_BG P02
        .byte $AA,$AA,$BF,$BF,$BF,$FF,$FF,$FF   ; $89 CROIX_BD P02
        .byte $00,$00,$00,$00,$00,$00,$00,$00   ; $8A (libre)
        .byte $00,$00,$00,$00,$00,$00,$00,$00   ; $8B (libre)
        .byte $00,$00,$00,$00,$00,$00,$00,$00   ; $8C (libre)
        .byte $00,$00,$00,$00,$00,$00,$00,$00   ; $8D (libre)
        .byte $00,$00,$00,$00,$00,$00,$00,$00   ; $8E (libre)
        .byte $00,$00,$00,$00,$00,$00,$00,$00   ; $8F (libre)
        .byte $30,$78,$CC,$CC,$FC,$CC,$CC,$CC   ; $90 A P09
        .byte $F8,$CC,$CC,$F8,$CC,$CC,$CC,$F8   ; $91 B P09
        .byte $7C,$C0,$C0,$C0,$C0,$C0,$C0,$7C   ; $92 C P09
        .byte $F8,$CC,$CC,$CC,$CC,$CC,$CC,$F8   ; $93 D P09
        .byte $FC,$C0,$C0,$F0,$F0,$C0,$C0,$FC   ; $94 E P09
        .byte $FC,$C0,$C0,$F0,$F0,$C0,$C0,$C0   ; $95 F P09
        .byte $7C,$C0,$C0,$CE,$CE,$C6,$C6,$7C   ; $96 G P09
        .byte $CC,$CC,$CC,$FC,$FC,$CC,$CC,$CC   ; $97 H P09
        .byte $FC,$30,$30,$30,$30,$30,$30,$FC   ; $98 I P09
        .byte $1C,$0C,$0C,$0C,$0C,$CC,$CC,$78   ; $99 J P09
        .byte $CC,$D8,$F0,$E0,$E0,$F0,$D8,$CC   ; $9A K P09
        .byte $C0,$C0,$C0,$C0,$C0,$C0,$C0,$FC   ; $9B L P09
        .byte $C6,$EE,$FE,$D6,$C6,$C6,$C6,$C6   ; $9C M P09
        .byte $C6,$E6,$E6,$F6,$DE,$CE,$CE,$C6   ; $9D N P09
        .byte $78,$CC,$CC,$CC,$CC,$CC,$CC,$78   ; $9E O P09
        .byte $F8,$CC,$CC,$F8,$C0,$C0,$C0,$C0   ; $9F P P09
        .byte $78,$CC,$CC,$CC,$DC,$CC,$78,$0C   ; $A0 Q P09
        .byte $F8,$CC,$CC,$F8,$F0,$D8,$CC,$CC   ; $A1 R P09
        .byte $7C,$C0,$C0,$78,$0C,$0C,$0C,$F8   ; $A2 S P09
        .byte $FC,$30,$30,$30,$30,$30,$30,$30   ; $A3 T P09
        .byte $CC,$CC,$CC,$CC,$CC,$CC,$CC,$78   ; $A4 U P09
        .byte $CC,$CC,$CC,$CC,$6C,$78,$78,$30   ; $A5 V P09
        .byte $C6,$C6,$C6,$C6,$D6,$FE,$EE,$C6   ; $A6 W P09
        .byte $CC,$CC,$78,$30,$30,$78,$CC,$CC   ; $A7 X P09
        .byte $CC,$CC,$CC,$78,$30,$30,$30,$30   ; $A8 Y P09
        .byte $FC,$0C,$18,$30,$30,$60,$C0,$FC   ; $A9 Z P09
        .byte $55,$AA,$AA,$AA,$AA,$AA,$AA,$AA   ; $AA TROTTOIR_H_HAUT P05
        .byte $AA,$AA,$AA,$AA,$AA,$AA,$AA,$55   ; $AB TROTTOIR_H_BAS P05
        .byte $6A,$6A,$6A,$6A,$6A,$6A,$6A,$6A   ; $AC TROTTOIR_V_GAUCHE P05
        .byte $A9,$A9,$A9,$A9,$A9,$A9,$A9,$A9   ; $AD TROTTOIR_V_DROITE P05
        .byte $AA,$AA,$AA,$AA,$AA,$AA,$AA,$AA   ; $AE TROTTOIR_PLEIN P05
        .byte $55,$6A,$6A,$6A,$6A,$6A,$6A,$6A   ; $AF TROTTOIR_COIN_NO P05
        .byte $55,$A9,$A9,$A9,$A9,$A9,$A9,$A9   ; $B0 TROTTOIR_COIN_NE P05
        .byte $FF,$EF,$FF,$FB,$FF,$BF,$FF,$FE   ; $B1 CHAMP_BLE P07
        .byte $00,$00,$00,$FF,$FF,$00,$00,$00   ; $B2 CLOTURE_H P02
        .byte $3C,$3C,$3C,$3C,$3C,$3C,$3C,$3C   ; $B3 CLOTURE_V P02
        .byte $00,$00,$00,$3F,$3F,$3C,$3C,$3C   ; $B4 CLOTURE_NO P02
        .byte $00,$00,$00,$FC,$FC,$3C,$3C,$3C   ; $B5 CLOTURE_NE P02
        .byte $3C,$3C,$3C,$3F,$3F,$00,$00,$00   ; $B6 CLOTURE_SO P02
        .byte $3C,$3C,$3C,$FC,$FC,$00,$00,$00   ; $B7 CLOTURE_SE P02
        .byte $AA,$AA,$95,$95,$95,$95,$95,$95   ; $B8 PARKING_HG P02
        .byte $AA,$AA,$55,$55,$55,$55,$55,$55   ; $B9 PARKING_HD P02
        .byte $95,$95,$95,$95,$95,$95,$95,$95   ; $BA PARKING_BG P02
        .byte $55,$55,$55,$55,$55,$55,$55,$55   ; $BB PARKING_BD P02
        .byte $FF,$FF,$EA,$EA,$EF,$EF,$EF,$EA   ; $BC PANNEAU_PARKING_HG P10
        .byte $FF,$FF,$AB,$AB,$FB,$FB,$FB,$AB   ; $BD PANNEAU_PARKING_HD P10
        .byte $EF,$EF,$EF,$EF,$EF,$EF,$FF,$FF   ; $BE PANNEAU_PARKING_BG P10
        .byte $FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF   ; $BF PANNEAU_PARKING_BD P10
        .byte $AA,$AA,$6F,$7F,$7A,$7A,$7A,$7F   ; $C0 VOITURE_HG P02
        .byte $AA,$AA,$F9,$FD,$AD,$AD,$AD,$FD   ; $C1 VOITURE_HD P02
        .byte $7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F   ; $C2 VOITURE_MG P02
        .byte $FD,$FD,$FD,$FD,$FD,$FD,$FD,$FD   ; $C3 VOITURE_MD P02
        .byte $7A,$7A,$7A,$7A,$7F,$7F,$7F,$6F   ; $C4 VOITURE_BG P02
        .byte $AD,$AD,$AD,$AD,$FD,$FD,$FD,$F9   ; $C5 VOITURE_BD P02
        .byte $00,$01,$03,$06,$0E,$3C,$74,$64   ; $C6 LOGO_CLOSEAI_HG P09
        .byte $78,$FE,$07,$0F,$1C,$70,$C3,$CE   ; $C7 LOGO_CLOSEAI_HC P09
        .byte $00,$00,$E0,$F8,$18,$0C,$84,$E6   ; $C8 LOGO_CLOSEAI_HD P09
        .byte $C4,$C4,$C4,$C4,$47,$61,$38,$7E   ; $C9 LOGO_CLOSEAI_MG P09
        .byte $DC,$E6,$C3,$C1,$C3,$C3,$67,$39   ; $CA LOGO_CLOSEAI_MC P09
        .byte $7E,$1C,$86,$C2,$23,$23,$23,$23   ; $CB LOGO_CLOSEAI_MD P09
        .byte $67,$21,$30,$18,$1F,$07,$00,$00   ; $CC LOGO_CLOSEAI_BG P09
        .byte $73,$C3,$0E,$3C,$F0,$E0,$7F,$1F   ; $CD LOGO_CLOSEAI_BC P09
        .byte $26,$26,$3C,$70,$60,$C0,$80,$00   ; $CE LOGO_CLOSEAI_BD P09
        .byte $00,$00,$00,$00,$00,$00,$00,$07   ; $CF LOGO_POMME_HG P01
        .byte $00,$07,$0F,$1F,$1F,$1E,$1C,$FF   ; $D0 LOGO_POMME_HC P01
        .byte $00,$00,$80,$80,$00,$00,$00,$F0   ; $D1 LOGO_POMME_HD P01
        .byte $0F,$1F,$1F,$1F,$3F,$3F,$3F,$3F   ; $D2 LOGO_POMME_MG P11
        .byte $FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF   ; $D3 LOGO_POMME_MC P11
        .byte $F8,$F8,$F0,$E0,$C0,$C0,$E0,$E0   ; $D4 LOGO_POMME_MD P11
        .byte $1F,$1F,$1F,$0F,$0F,$07,$03,$00   ; $D5 LOGO_POMME_BG P03
        .byte $FF,$FF,$FF,$FF,$FF,$FF,$FF,$00   ; $D6 LOGO_POMME_BC P03
        .byte $F8,$F8,$F8,$F8,$F0,$E0,$C0,$00   ; $D7 LOGO_POMME_BD P03
        .byte $00,$00,$07,$0F,$0F,$3F,$3F,$7E   ; $D8 LOGO_GOGLE_HG P03
        .byte $00,$FF,$FF,$FF,$F7,$00,$00,$00   ; $D9 LOGO_GOGLE_HC P03
        .byte $00,$80,$E0,$E0,$E0,$C0,$00,$00   ; $DA LOGO_GOGLE_HD P03
        .byte $78,$78,$78,$70,$70,$78,$78,$78   ; $DB LOGO_GOGLE_MG P11
        .byte $00,$00,$0F,$0F,$0F,$0F,$00,$00   ; $DC LOGO_GOGLE_MC P12
        .byte $00,$00,$FE,$FE,$FE,$FE,$1E,$3E   ; $DD LOGO_GOGLE_MD P12
        .byte $7C,$3E,$1F,$0F,$07,$03,$00,$00   ; $DE LOGO_GOGLE_BG P01
        .byte $00,$00,$00,$FF,$FF,$FF,$7E,$00   ; $DF LOGO_GOGLE_BC P01
        .byte $7C,$7C,$FC,$F8,$F0,$C0,$00,$00   ; $E0 LOGO_GOGLE_BD P01
        .byte $00,$00,$00,$00,$0E,$0E,$0E,$0F   ; $E1 LOGO_LECAT_HG P11
        .byte $00,$00,$00,$00,$00,$00,$00,$C3   ; $E2 LOGO_LECAT_HC P11
        .byte $00,$00,$00,$00,$70,$70,$70,$F0   ; $E3 LOGO_LECAT_HD P11
        .byte $0F,$0F,$0F,$0F,$0F,$0F,$0E,$0E   ; $E4 LOGO_LECAT_MG P13
        .byte $C3,$C3,$C7,$FF,$FF,$FF,$38,$38   ; $E5 LOGO_LECAT_MC P13
        .byte $F0,$F0,$F0,$F0,$F0,$F0,$70,$70   ; $E6 LOGO_LECAT_MD P13
        .byte $0E,$7F,$7F,$7F,$00,$00,$00,$00   ; $E7 LOGO_LECAT_BG P03
        .byte $38,$C7,$C7,$C7,$00,$00,$00,$00   ; $E8 LOGO_LECAT_BC P03
        .byte $70,$FE,$FE,$FE,$00,$00,$00,$00   ; $E9 LOGO_LECAT_BD P03
        .byte $00,$00,$00,$00,$00,$01,$03,$07   ; $EA LOGO_GLOCK_HG P09
        .byte $00,$00,$00,$18,$FF,$FF,$C0,$00   ; $EB LOGO_GLOCK_HC P09
        .byte $00,$00,$02,$04,$8C,$98,$38,$78   ; $EC LOGO_GLOCK_HD P09
        .byte $0E,$0C,$0C,$1C,$1C,$1C,$0C,$0C   ; $ED LOGO_GLOCK_MG P09
        .byte $00,$01,$03,$06,$08,$10,$20,$00   ; $EE LOGO_GLOCK_MC P09
        .byte $F8,$F8,$18,$18,$18,$18,$18,$38   ; $EF LOGO_GLOCK_MD P09
        .byte $0E,$0E,$0C,$08,$10,$20,$00,$00   ; $F0 LOGO_GLOCK_BG P09
        .byte $00,$00,$01,$FF,$FF,$00,$00,$00   ; $F1 LOGO_GLOCK_BC P09
        .byte $70,$70,$E0,$C0,$00,$00,$00,$00   ; $F2 LOGO_GLOCK_BD P09
        .byte $00,$00,$01,$01,$02,$04,$04,$68   ; $F3 LOGO_GWEN_HG P14
        .byte $F8,$F8,$3C,$3F,$3F,$7F,$00,$00   ; $F4 LOGO_GWEN_HC P14
        .byte $00,$00,$00,$F8,$F8,$FC,$04,$04   ; $F5 LOGO_GWEN_HD P14
        .byte $F0,$F0,$78,$78,$3C,$3C,$1E,$1F   ; $F6 LOGO_GWEN_MG P14
        .byte $00,$00,$7E,$7E,$3C,$3C,$18,$00   ; $F7 LOGO_GWEN_MC P14
        .byte $08,$08,$04,$04,$22,$22,$71,$FF   ; $F8 LOGO_GWEN_MD P14
        .byte $3F,$3F,$38,$10,$1F,$00,$00,$00   ; $F9 LOGO_GWEN_BG P14
        .byte $00,$81,$01,$03,$C3,$27,$1F,$1F   ; $FA LOGO_GWEN_BC P14
        .byte $FE,$FC,$E0,$C0,$C0,$80,$80,$00   ; $FB LOGO_GWEN_BD P14

_tileset_colors:
        .byte $05,$0A,$0A,$0A,$0A,$0A,$0A,$0A   ; $40-$47
        .byte $0A,$0A,$0A,$0A,$0A,$05,$05,$02   ; $48-$4F
        .byte $02,$02,$0A,$0B,$08,$0A,$08,$08   ; $50-$57
        .byte $08,$08,$08,$0A,$0F,$0D,$08,$0D   ; $58-$5F
        .byte $0B,$0B,$0B,$0B,$0B,$0B,$0B,$0B   ; $60-$67
        .byte $0B,$0B,$0B,$0B,$0B,$0B,$0B,$0B   ; $68-$6F
        .byte $0B,$0B,$0B,$0B,$0B,$0B,$0B,$0B   ; $70-$77
        .byte $0B,$0F,$0F,$0F,$05,$05,$05,$05   ; $78-$7F
        .byte $08,$08,$08,$08,$08,$08,$0A,$0A   ; $80-$87
        .byte $0A,$0A,$00,$00,$00,$00,$00,$00   ; $88-$8F
        .byte $00,$00,$00,$00,$00,$00,$00,$00   ; $90-$97
        .byte $00,$00,$00,$00,$00,$00,$00,$00   ; $98-$9F
        .byte $00,$00,$00,$00,$00,$00,$00,$00   ; $A0-$A7
        .byte $00,$00,$08,$08,$08,$08,$08,$08   ; $A8-$AF
        .byte $08,$0F,$0A,$0A,$0A,$0A,$0A,$0A   ; $B0-$B7
        .byte $0A,$0A,$0A,$0A,$0E,$0E,$0E,$0E   ; $B8-$BF
        .byte $0A,$0A,$0A,$0A,$0A,$0A,$00,$00   ; $C0-$C7
        .byte $00,$00,$00,$00,$00,$00,$00,$05   ; $C8-$CF
        .byte $05,$05,$07,$07,$07,$02,$02,$02   ; $D0-$D7
        .byte $02,$02,$02,$07,$06,$06,$05,$05   ; $D8-$DF
        .byte $05,$07,$07,$07,$04,$04,$04,$02   ; $E0-$E7
        .byte $02,$02,$00,$00,$00,$00,$00,$00   ; $E8-$EF
        .byte $00,$00,$00,$04,$04,$04,$04,$04   ; $F0-$F7
        .byte $04,$04,$04,$04   ; $F8-$FB
