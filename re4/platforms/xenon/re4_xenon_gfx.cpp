// First native graphics milestone for RE4 on Xbox 360.
// Uses Vulkan4Xenon directly: no Aurora GX command stream and no GX emulation here.
// Milestone: initialize the Xenos display/swapchain and present a known clear colour.
#include "re4_xenon_gfx.h"

#include <vulkan/vulkan.h>
#include <xsdk/log.h>
#include <string.h>

namespace {
struct GfxState {
    VkInstance instance;
    VkPhysicalDevice physical;
    VkDevice device;
    VkQueue queue;
    VkSurfaceKHR surface;
    VkSwapchainKHR swapchain;
    VkRenderPass renderPass;
    VkCommandPool commandPool;
    VkSemaphore acquired;
    VkSemaphore rendered;
    VkFence fence;
    VkImage images[3];
    VkImageView views[3];
    VkFramebuffer framebuffers[3];
    VkCommandBuffer commands[3];
    uint32_t imageCount;
    uint32_t width;
    uint32_t height;
    bool ready;
};
GfxState g{};

bool ok(const char* label, VkResult result) {
    if (result == VK_SUCCESS) return true;
    xsdk_log_write("[RE4-GFX] %s failed: %d", label, (int)result);
    return false;
}

void destroy() {
    if (g.device != VK_NULL_HANDLE) {
        vkDeviceWaitIdle(g.device);
        if (g.fence) vkDestroyFence(g.device, g.fence, nullptr);
        if (g.acquired) vkDestroySemaphore(g.device, g.acquired, nullptr);
        if (g.rendered) vkDestroySemaphore(g.device, g.rendered, nullptr);
        if (g.commandPool) vkDestroyCommandPool(g.device, g.commandPool, nullptr);
        for (uint32_t i = 0; i < g.imageCount; ++i) {
            if (g.framebuffers[i]) vkDestroyFramebuffer(g.device, g.framebuffers[i], nullptr);
            if (g.views[i]) vkDestroyImageView(g.device, g.views[i], nullptr);
        }
        if (g.renderPass) vkDestroyRenderPass(g.device, g.renderPass, nullptr);
        if (g.swapchain) vkDestroySwapchainKHR(g.device, g.swapchain, nullptr);
        vkDestroyDevice(g.device, nullptr);
    }
    if (g.instance) {
        if (g.surface) vkDestroySurfaceKHR(g.instance, g.surface, nullptr);
        vkDestroyInstance(g.instance, nullptr);
    }
    memset(&g, 0, sizeof(g));
}

bool create_instance() {
    const char* extensions[] = { VK_KHR_SURFACE_EXTENSION_NAME, VK_KHR_DISPLAY_EXTENSION_NAME };
    VkApplicationInfo app{};
    app.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    app.pApplicationName = "RE4 Xenon Native Renderer";
    app.apiVersion = VK_API_VERSION_1_0;
    VkInstanceCreateInfo ci{};
    ci.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    ci.pApplicationInfo = &app;
    ci.enabledExtensionCount = 2;
    ci.ppEnabledExtensionNames = extensions;
    return ok("vkCreateInstance", vkCreateInstance(&ci, nullptr, &g.instance));
}

bool create_device() {
    uint32_t count = 1;
    if (!ok("vkEnumeratePhysicalDevices", vkEnumeratePhysicalDevices(g.instance, &count, &g.physical)) || count == 0)
        return false;
    const float priority = 1.0f;
    VkDeviceQueueCreateInfo qi{};
    qi.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
    qi.queueFamilyIndex = 0;
    qi.queueCount = 1;
    qi.pQueuePriorities = &priority;
    const char* extensions[] = { VK_KHR_SWAPCHAIN_EXTENSION_NAME };
    VkDeviceCreateInfo di{};
    di.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
    di.queueCreateInfoCount = 1;
    di.pQueueCreateInfos = &qi;
    di.enabledExtensionCount = 1;
    di.ppEnabledExtensionNames = extensions;
    if (!ok("vkCreateDevice", vkCreateDevice(g.physical, &di, nullptr, &g.device))) return false;
    vkGetDeviceQueue(g.device, 0, 0, &g.queue);
    return true;
}

bool create_display_surface() {
    uint32_t count = 1;
    VkDisplayPropertiesKHR display{};
    if (!ok("vkGetPhysicalDeviceDisplayPropertiesKHR",
            vkGetPhysicalDeviceDisplayPropertiesKHR(g.physical, &count, &display)) || count == 0) return false;
    count = 1;
    VkDisplayModePropertiesKHR mode{};
    if (!ok("vkGetDisplayModePropertiesKHR",
            vkGetDisplayModePropertiesKHR(g.physical, display.display, &count, &mode)) || count == 0) return false;
    g.width = mode.parameters.visibleRegion.width;
    g.height = mode.parameters.visibleRegion.height;
    xsdk_log_write("[RE4-GFX] display %s: %ux%u", display.displayName, g.width, g.height);
    VkDisplaySurfaceCreateInfoKHR si{};
    si.sType = VK_STRUCTURE_TYPE_DISPLAY_SURFACE_CREATE_INFO_KHR;
    si.displayMode = mode.displayMode;
    si.planeIndex = 0;
    si.transform = VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR;
    si.alphaMode = VK_DISPLAY_PLANE_ALPHA_OPAQUE_BIT_KHR;
    si.imageExtent = mode.parameters.visibleRegion;
    return ok("vkCreateDisplayPlaneSurfaceKHR",
              vkCreateDisplayPlaneSurfaceKHR(g.instance, &si, nullptr, &g.surface));
}

bool create_swapchain() {
    VkSurfaceCapabilitiesKHR caps{};
    if (!ok("vkGetPhysicalDeviceSurfaceCapabilitiesKHR",
            vkGetPhysicalDeviceSurfaceCapabilitiesKHR(g.physical, g.surface, &caps))) return false;
    uint32_t formatCount = 0;
    if (!ok("vkGetPhysicalDeviceSurfaceFormatsKHR",
            vkGetPhysicalDeviceSurfaceFormatsKHR(g.physical, g.surface, &formatCount, nullptr)) || formatCount == 0)
        return false;
    VkSurfaceFormatKHR formats[8]{};
    if (formatCount > 8) formatCount = 8;
    if (!ok("vkGetPhysicalDeviceSurfaceFormatsKHR(list)",
            vkGetPhysicalDeviceSurfaceFormatsKHR(g.physical, g.surface, &formatCount, formats))) return false;
    VkSurfaceFormatKHR chosen = formats[0];
    for (uint32_t i = 0; i < formatCount; ++i)
        if (formats[i].format == VK_FORMAT_B8G8R8A8_UNORM) chosen = formats[i];
    VkSwapchainCreateInfoKHR ci{};
    ci.sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR;
    ci.surface = g.surface;
    ci.minImageCount = caps.minImageCount > 2 ? caps.minImageCount : 2;
    if (caps.maxImageCount && ci.minImageCount > caps.maxImageCount) ci.minImageCount = caps.maxImageCount;
    ci.imageFormat = chosen.format;
    ci.imageColorSpace = chosen.colorSpace;
    ci.imageExtent = caps.currentExtent.width != 0xFFFFFFFFu ? caps.currentExtent : VkExtent2D{g.width, g.height};
    ci.imageArrayLayers = 1;
    ci.imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT;
    ci.preTransform = caps.currentTransform;
    ci.compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
    ci.presentMode = VK_PRESENT_MODE_FIFO_KHR;
    ci.clipped = VK_TRUE;
    if (!ok("vkCreateSwapchainKHR", vkCreateSwapchainKHR(g.device, &ci, nullptr, &g.swapchain))) return false;
    g.width = ci.imageExtent.width;
    g.height = ci.imageExtent.height;
    g.imageCount = 3;
    if (!ok("vkGetSwapchainImagesKHR", vkGetSwapchainImagesKHR(g.device, g.swapchain, &g.imageCount, g.images))) return false;
    return g.imageCount > 0 && g.imageCount <= 3;
}

bool create_render_targets() {
    VkAttachmentDescription attachment{};
    attachment.format = VK_FORMAT_B8G8R8A8_UNORM;
    attachment.samples = VK_SAMPLE_COUNT_1_BIT;
    attachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
    attachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
    attachment.stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
    attachment.stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
    attachment.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    attachment.finalLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
    VkAttachmentReference ref{0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
    VkSubpassDescription subpass{};
    subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
    subpass.colorAttachmentCount = 1;
    subpass.pColorAttachments = &ref;
    VkRenderPassCreateInfo rp{};
    rp.sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO;
    rp.attachmentCount = 1;
    rp.pAttachments = &attachment;
    rp.subpassCount = 1;
    rp.pSubpasses = &subpass;
    if (!ok("vkCreateRenderPass", vkCreateRenderPass(g.device, &rp, nullptr, &g.renderPass))) return false;
    for (uint32_t i = 0; i < g.imageCount; ++i) {
        VkImageViewCreateInfo vi{};
        vi.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
        vi.image = g.images[i];
        vi.viewType = VK_IMAGE_VIEW_TYPE_2D;
        vi.format = VK_FORMAT_B8G8R8A8_UNORM;
        vi.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        if (!ok("vkCreateImageView", vkCreateImageView(g.device, &vi, nullptr, &g.views[i]))) return false;
        VkFramebufferCreateInfo fi{};
        fi.sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO;
        fi.renderPass = g.renderPass;
        fi.attachmentCount = 1;
        fi.pAttachments = &g.views[i];
        fi.width = g.width;
        fi.height = g.height;
        fi.layers = 1;
        if (!ok("vkCreateFramebuffer", vkCreateFramebuffer(g.device, &fi, nullptr, &g.framebuffers[i]))) return false;
    }
    return true;
}

bool create_commands() {
    VkCommandPoolCreateInfo pi{};
    pi.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
    pi.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    if (!ok("vkCreateCommandPool", vkCreateCommandPool(g.device, &pi, nullptr, &g.commandPool))) return false;
    VkCommandBufferAllocateInfo ai{};
    ai.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    ai.commandPool = g.commandPool;
    ai.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    ai.commandBufferCount = g.imageCount;
    if (!ok("vkAllocateCommandBuffers", vkAllocateCommandBuffers(g.device, &ai, g.commands))) return false;
    for (uint32_t i = 0; i < g.imageCount; ++i) {
        VkCommandBufferBeginInfo bi{};
        bi.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        if (!ok("vkBeginCommandBuffer", vkBeginCommandBuffer(g.commands[i], &bi))) return false;
        VkClearValue clear{};
        VkRenderPassBeginInfo pass{};
        pass.sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO;
        pass.renderPass = g.renderPass;
        pass.framebuffer = g.framebuffers[i];
        pass.renderArea.extent = {g.width, g.height};
        pass.clearValueCount = 1;
        pass.pClearValues = &clear;
        vkCmdBeginRenderPass(g.commands[i], &pass, VK_SUBPASS_CONTENTS_INLINE);
        vkCmdEndRenderPass(g.commands[i]);
        if (!ok("vkEndCommandBuffer", vkEndCommandBuffer(g.commands[i]))) return false;
    }
    VkSemaphoreCreateInfo sem{};
    sem.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;
    if (!ok("vkCreateSemaphore(acquire)", vkCreateSemaphore(g.device, &sem, nullptr, &g.acquired))) return false;
    if (!ok("vkCreateSemaphore(render)", vkCreateSemaphore(g.device, &sem, nullptr, &g.rendered))) return false;
    VkFenceCreateInfo fence{};
    fence.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
    fence.flags = VK_FENCE_CREATE_SIGNALED_BIT;
    return ok("vkCreateFence", vkCreateFence(g.device, &fence, nullptr, &g.fence));
}
}

extern "C" int re4_xenon_gfx_init(void) {
    destroy();
    xsdk_log_write("[RE4-GFX] native renderer init");
    if (!create_instance() || !create_device() || !create_display_surface() ||
        !create_swapchain() || !create_render_targets() || !create_commands()) {
        xsdk_log_write("[RE4-GFX] native renderer init failed");
        destroy();
        return 0;
    }
    g.ready = true;
    xsdk_log_write("[RE4-GFX] native renderer ready: %ux%u, %u images", g.width, g.height, g.imageCount);
    return 1;
}

extern "C" int re4_xenon_gfx_clear_frame(float r, float green, float b, float a) {
    if (!g.ready) return 0;
    if (!ok("vkWaitForFences", vkWaitForFences(g.device, 1, &g.fence, VK_TRUE, UINT64_MAX))) return 0;
    if (!ok("vkResetFences", vkResetFences(g.device, 1, &g.fence))) return 0;
    uint32_t index = 0;
    if (!ok("vkAcquireNextImageKHR", vkAcquireNextImageKHR(g.device, g.swapchain, UINT64_MAX, g.acquired, VK_NULL_HANDLE, &index))) return 0;
    if (!ok("vkResetCommandBuffer", vkResetCommandBuffer(g.commands[index], 0))) return 0;
    VkCommandBufferBeginInfo bi{};
    bi.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    if (!ok("vkBeginCommandBuffer(frame)", vkBeginCommandBuffer(g.commands[index], &bi))) return 0;
    VkClearValue clear{};
    clear.color.float32[0] = r; clear.color.float32[1] = green; clear.color.float32[2] = b; clear.color.float32[3] = a;
    VkRenderPassBeginInfo pass{};
    pass.sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO;
    pass.renderPass = g.renderPass;
    pass.framebuffer = g.framebuffers[index];
    pass.renderArea.extent = {g.width, g.height};
    pass.clearValueCount = 1;
    pass.pClearValues = &clear;
    vkCmdBeginRenderPass(g.commands[index], &pass, VK_SUBPASS_CONTENTS_INLINE);
    vkCmdEndRenderPass(g.commands[index]);
    if (!ok("vkEndCommandBuffer(frame)", vkEndCommandBuffer(g.commands[index]))) return 0;
    const VkPipelineStageFlags waitStage = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
    VkSubmitInfo submit{};
    submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submit.waitSemaphoreCount = 1;
    submit.pWaitSemaphores = &g.acquired;
    submit.pWaitDstStageMask = &waitStage;
    submit.commandBufferCount = 1;
    submit.pCommandBuffers = &g.commands[index];
    submit.signalSemaphoreCount = 1;
    submit.pSignalSemaphores = &g.rendered;
    if (!ok("vkQueueSubmit", vkQueueSubmit(g.queue, 1, &submit, g.fence))) return 0;
    VkPresentInfoKHR present{};
    present.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;
    present.waitSemaphoreCount = 1;
    present.pWaitSemaphores = &g.rendered;
    present.swapchainCount = 1;
    present.pSwapchains = &g.swapchain;
    present.pImageIndices = &index;
    return ok("vkQueuePresentKHR", vkQueuePresentKHR(g.queue, &present)) ? 1 : 0;
}

extern "C" void re4_xenon_gfx_shutdown(void) {
    destroy();
}
