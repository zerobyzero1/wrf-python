! NCLFORTSTART
SUBROUTINE DCALRELHL(u, v, ght, ter, top, sreh, miy, mjx, mkzh)
    USE constants, ONLY : PI, RAD_PER_DEG, DEG_PER_RAD

    IMPLICIT NONE

    !f2py threadsafe
    !f2py intent(in,out) :: sreh

    INTEGER, INTENT(IN) :: miy, mjx, mkzh
    REAL(KIND=8), DIMENSION(miy,mjx,mkzh), INTENT(IN) :: u, v, ght
    REAL(KIND=8), INTENT(IN) :: top
    REAL(KIND=8), DIMENSION(miy,mjx), INTENT(IN) :: ter
    REAL(KIND=8), DIMENSION(miy,mjx), INTENT(OUT) :: sreh

! NCLEND

    ! This helicity code was provided by Dr. Craig Mattocks, and
    ! verified by Cindy Bruyere to produce results equivalent to
    ! those generated by RIP4. (The code came from RIP4?)

    REAL(KIND=8) :: dh, sdh, su, sv, ua, va, asp, adr, bsp, bdr
    REAL(KIND=8) :: cu, cv, x, sum
    INTEGER :: i, j, k, k10, k3, ktop
    !REAL(KIND=8), PARAMETER :: DTR=PI/180.d0, DPR=180.d0/PI

    DO j = 1, mjx-1
        DO i = 1, miy-1
            sdh = 0.d0
            su = 0.d0
            sv = 0.d0
            k3 = 0
            k10 = 0
            ktop = 0
            DO k = mkzh, 2, -1
                IF (((ght(i,j,k) - ter(i,j)) .GT. 10000.D0) .AND. (k10 .EQ. 0)) THEN
                    k10 = k
                    EXIT
                ENDIF
                IF (((ght(i,j,k) - ter(i,j)) .GT. top) .AND. (ktop .EQ. 0)) THEN
                    ktop = k
                ENDIF
                IF (((ght(i,j,k) - ter(i,j)) .GT. 3000.D0) .AND. (k3 .EQ. 0)) THEN
                    k3 = k
                ENDIF
            END DO

            IF (k10 .EQ. 0) THEN
                k10 = 2
            ENDIF
            DO k = k3, k10, -1
                dh = ght(i,j,k-1) - ght(i,j,k)
                sdh = sdh + dh
                su = su + 0.5D0*dh*(u(i,j,k-1) + u(i,j,k))
                sv = sv + 0.5D0*dh*(v(i,j,k-1) + v(i,j,k))
            END DO
            ua = su / sdh
            va = sv / sdh
            asp = SQRT(ua*ua + va*va)
            IF (ua .EQ. 0.D0 .AND. va .EQ. 0.D0) THEN
                adr = 0.D0
            ELSE
                adr = DEG_PER_RAD * (PI + ATAN2(ua,va))
            ENDIF
            bsp = 0.75D0 * asp
            bdr = adr + 30.D0
            IF (bdr .GT. 360.D0) THEN
                bdr = bdr - 360.D0
            ENDIF
            cu = -bsp * SIN(bdr * RAD_PER_DEG)
            cv = -bsp * COS(bdr * RAD_PER_DEG)
            sum = 0.D0
            DO k = mkzh-1, ktop, -1
                x = ((u(i,j,k) - cu) * (v(i,j,k) - v(i,j,k+1))) - &
                                     ((v(i,j,k) - cv) * (u(i,j,k) - u(i,j,k+1)))
                sum = sum + x
            END DO
            sreh(i,j) = -sum
        END DO
    END DO

    RETURN

END SUBROUTINE DCALRELHL