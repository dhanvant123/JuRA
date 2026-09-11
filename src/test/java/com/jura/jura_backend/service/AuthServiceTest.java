package com.jura.jura_backend.service;

import com.jura.jura_backend.dto.auth.AuthResponse;
import com.jura.jura_backend.dto.auth.LoginRequest;
import com.jura.jura_backend.dto.auth.RegisterRequest;
import com.jura.jura_backend.entity.User;
import com.jura.jura_backend.exception.UserAlreadyExistsException;
import com.jura.jura_backend.repository.UserRepository;
import com.jura.jura_backend.security.JwtService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.time.Instant;
import java.util.Collections;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AuthServiceTest {

    @Mock
    private UserRepository userRepository;

    @Mock
    private PasswordEncoder passwordEncoder;

    @Mock
    private JwtService jwtService;

    @Mock
    private AuthenticationManager authenticationManager;

    @Mock
    private UserDetailsService userDetailsService;

    @InjectMocks
    private AuthService authService;

    private User sampleUser;
    private UserDetails userDetails;

    @BeforeEach
    void setUp() {
        sampleUser = User.builder()
                .email("advocate@jura.law")
                .name("Adv. Sharma")
                .passwordHash("hashedSecret")
                .role("USER")
                .createdAt(Instant.now())
                .phNo("9876543210")
                .build();

        userDetails = new org.springframework.security.core.userdetails.User(
                sampleUser.getEmail(),
                sampleUser.getPasswordHash(),
                Collections.emptyList()
        );
    }

    @Test
    void shouldRegisterNewUserSuccessfully() {
        RegisterRequest request = RegisterRequest.builder()
                .email("advocate@jura.law")
                .name("Adv. Sharma")
                .password("secret123")
                .phoneNumber("9876543210")
                .build();

        when(userRepository.existsByEmail("advocate@jura.law")).thenReturn(false);
        when(userRepository.existsByPhNo("9876543210")).thenReturn(false);
        when(passwordEncoder.encode("secret123")).thenReturn("hashedSecret");
        when(userRepository.save(any(User.class))).thenReturn(sampleUser);
        when(userDetailsService.loadUserByUsername("advocate@jura.law")).thenReturn(userDetails);
        when(jwtService.generateToken(userDetails)).thenReturn("mock.jwt.token");
        when(jwtService.getExpirationTime()).thenReturn(3600000L);

        AuthResponse response = authService.register(request);

        assertNotNull(response);
        assertEquals("mock.jwt.token", response.getToken());
        assertEquals("advocate@jura.law", response.getUser().getEmail());
        verify(userRepository).save(any(User.class));
    }

    @Test
    void shouldThrowExceptionWhenRegisteringExistingEmail() {
        RegisterRequest request = RegisterRequest.builder()
                .email("advocate@jura.law")
                .name("Adv. Sharma")
                .password("secret123")
                .build();

        when(userRepository.existsByEmail("advocate@jura.law")).thenReturn(true);

        assertThrows(UserAlreadyExistsException.class, () -> authService.register(request));
    }

    @Test
    void shouldLoginSuccessfully() {
        LoginRequest request = LoginRequest.builder()
                .email("advocate@jura.law")
                .password("secret123")
                .build();

        when(authenticationManager.authenticate(any(UsernamePasswordAuthenticationToken.class))).thenReturn(null);
        when(userRepository.findByEmail("advocate@jura.law")).thenReturn(Optional.of(sampleUser));
        when(userDetailsService.loadUserByUsername("advocate@jura.law")).thenReturn(userDetails);
        when(jwtService.generateToken(userDetails)).thenReturn("mock.jwt.token");
        when(jwtService.getExpirationTime()).thenReturn(3600000L);

        AuthResponse response = authService.login(request);

        assertNotNull(response);
        assertEquals("mock.jwt.token", response.getToken());
        assertEquals("advocate@jura.law", response.getUser().getEmail());
    }

    @Test
    void shouldThrowBadCredentialsOnFailedAuth() {
        LoginRequest request = LoginRequest.builder()
                .email("advocate@jura.law")
                .password("wrongpassword")
                .build();

        when(authenticationManager.authenticate(any(UsernamePasswordAuthenticationToken.class)))
                .thenThrow(new BadCredentialsException("Bad credentials"));

        assertThrows(BadCredentialsException.class, () -> authService.login(request));
    }
}
