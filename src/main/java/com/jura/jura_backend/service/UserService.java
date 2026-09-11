package com.jura.jura_backend.service;

import com.jura.jura_backend.dto.user.UserResponse;
import com.jura.jura_backend.entity.User;
import com.jura.jura_backend.exception.ResourceNotFoundException;
import com.jura.jura_backend.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Service
@RequiredArgsConstructor
public class UserService {

    private final UserRepository userRepository;

    @Transactional(readOnly = true)
    public UserResponse getCurrentUser(String email) {
        User user = userRepository.findByEmail(email)
                .orElseThrow(() -> new ResourceNotFoundException("User not found with email: " + email));

        return UserResponse.builder()
                .email(user.getEmail())
                .name(user.getName())
                .phNo(user.getPhNo())
                .role(user.getRole())
                .createdAt(user.getCreatedAt())
                .build();
    }
}
