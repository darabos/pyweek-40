// A GLSL shader to use in Pyxel instead of crisp.frag.

vec4 colorAt(vec2 p) {
    if(isInScreen(p)) {
        return vec4(getScreenColor(p), 1.0).rgba;
    } else {
        return vec4(u_backgroundColor, 1.0);
    }
}

#define RGB(r,g,b) (vec4(float(r), float(g), float(b), 255.) / 255.0)

void main() {
    vec2 screenFragCoord, screenTexCoord;
    getScreenParams(screenFragCoord, screenTexCoord);
    vec2 texelSize = 1. * u_screenScale / u_screenSize;

    vec4 color = vec4(0.0);
    int S = 10;
    float K = 2.;

    for(int x = -S; x <= S; ++x) {
        for(int y = -S; y <= S; ++y) {
            vec2 o = vec2(x, y);
            vec2 p = screenTexCoord + o * texelSize;
            vec4 c = colorAt(p);
            if (c != RGB(238,238,238) && c != RGB(237,199,176) && c != RGB(169,193,255)) {
                c *= c;
                color += c * K / max(K, length(o));
            }
        }
    }
    gl_FragColor = color / 90.;
    vec4 c = colorAt(screenTexCoord);
    gl_FragColor += c;
}
